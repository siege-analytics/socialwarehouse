"""
Spark-based geographic enrichment for warehouse-scale operations.

For datasets under ~1M rows, use the PostGIS-based Django management
commands (assign_boundaries, geocode_addresses). For larger datasets,
this module provides Spark + Sedona spatial joins.

Usage:
    from socialwarehouse.delta.enrichment import enrich_addresses_with_boundaries

    spark = get_spark_session(enable_sedona=True)
    enriched = enrich_addresses_with_boundaries(spark, "silver.addresses", year=2020)
    enriched.write.format("delta").save(get_table_path("gold", "enriched_addresses"))
"""

import logging

logger = logging.getLogger("socialwarehouse.delta")


def enrich_addresses_with_boundaries(spark, addresses_table, year=2020, boundaries_path=None):
    """Join geocoded addresses with boundary names via Sedona spatial join.

    Args:
        spark: SparkSession with Sedona registered.
        addresses_table: Delta path or table name for silver addresses.
        year: Census vintage year for boundaries.
        boundaries_path: Delta path for boundaries. If None, reads from
            silver.boundaries in the registry.

    Returns:
        DataFrame with address fields + boundary names.
    """
    from .config import get_table_path
    from .tables import TABLES

    # Read addresses
    if addresses_table in TABLES:
        addr_path = TABLES[addresses_table]["path"]
    else:
        addr_path = addresses_table

    addresses = (
        spark.read.format("delta").load(addr_path)
        .filter("latitude IS NOT NULL AND longitude IS NOT NULL")
    )

    # Create point geometry column
    addresses = addresses.selectExpr(
        "*",
        "ST_Point(CAST(longitude AS DOUBLE), CAST(latitude AS DOUBLE)) AS geom_point",
    )
    addresses.createOrReplaceTempView("addresses")

    # Read boundaries
    if boundaries_path is None:
        boundaries_path = get_table_path("silver", "boundaries")

    boundaries = (
        spark.read.format("delta").load(boundaries_path)
        .filter(f"vintage_year = {year}")
        .filter("wkt IS NOT NULL")
    )
    boundaries = boundaries.selectExpr(
        "*",
        "ST_GeomFromWKT(wkt) AS geom_boundary",
    )
    boundaries.createOrReplaceTempView("boundaries")

    # Spatial join — state
    state_join = spark.sql("""
        SELECT a.*, b.name AS state_name
        FROM addresses a
        LEFT JOIN boundaries b
            ON ST_Contains(b.geom_boundary, a.geom_point)
            AND b.summary_level = 'state'
            AND b.vintage_year = {year}
    """.format(year=year))

    # Spatial join — county
    county_join = spark.sql("""
        SELECT b.geoid AS county_geoid_joined, b.name AS county_name
        FROM addresses a
        JOIN boundaries b
            ON ST_Contains(b.geom_boundary, a.geom_point)
            AND b.summary_level = 'county'
            AND b.vintage_year = {year}
    """.format(year=year))

    # Spatial join — congressional district
    cd_join = spark.sql("""
        SELECT b.geoid AS cd_geoid_joined, b.name AS cd_name
        FROM addresses a
        JOIN boundaries b
            ON ST_Contains(b.geom_boundary, a.geom_point)
            AND b.summary_level = 'cd'
            AND b.vintage_year = {year}
    """.format(year=year))

    logger.info(
        "Enrichment complete: %d addresses joined with %d year boundaries",
        addresses.count(), year,
    )

    return state_join


def load_postgis_addresses_to_delta(spark, batch_size=100_000):
    """Export addresses from PostGIS to Delta Lake bronze tier.

    Reads from the Django Address model via JDBC and writes to the
    bronze.addresses Delta table.

    Args:
        spark: SparkSession.
        batch_size: Rows per JDBC fetch partition.

    Returns:
        Number of rows written.
    """
    import os

    jdbc_url = "jdbc:postgresql://{host}:{port}/{db}".format(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        db=os.environ.get("POSTGRES_DB", "socialwarehouse"),
    )

    from .config import get_table_path

    df = (
        spark.read
        .format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", "sw_geo_address")
        .option("user", os.environ.get("POSTGRES_USER", "socialwarehouse"))
        .option("password", os.environ.get("POSTGRES_PASSWORD", ""))
        .option("fetchsize", str(batch_size))
        .load()
    )

    path = get_table_path("bronze", "addresses")
    df.write.format("delta").mode("overwrite").partitionBy("state_abbreviation").save(path)

    count = df.count()
    logger.info("Exported %d addresses from PostGIS to %s", count, path)
    return count


def estimate_scale(row_count):
    """Recommend PostGIS vs Spark based on dataset size.

    Args:
        row_count: Number of addresses to process.

    Returns:
        Tuple of (engine, reason) where engine is 'postgis' or 'spark'.
    """
    if row_count < 1_000_000:
        return ("postgis", f"{row_count:,} rows — PostGIS spatial join is faster for < 1M")
    else:
        return ("spark", f"{row_count:,} rows — Spark/Sedona spatial join for >= 1M")
