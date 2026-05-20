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
    """Spatial-enrich addresses with state, county, and CD boundary attributes.

    Performs three sequential Sedona LEFT JOINs (state -> county -> cd). The
    returned DataFrame has the input address columns plus:
        state_name, county_geoid, county_name, cd_geoid, cd_name
    Addresses that don't intersect a polygon at a given summary level get
    NULL for that level's columns (LEFT JOIN semantics, consistent across
    the three passes).

    Args:
        spark: SparkSession with Sedona registered. Caller is responsible
            for registration; absence surfaces as ``AnalysisException:
            Undefined function: ST_Contains``.
        addresses_table: Either a key in ``delta/tables.py:TABLES`` or a
            raw Delta path.
        year: Census vintage year for boundaries (default 2020).
        boundaries_path: Optional Delta path for boundaries. Defaults to
            ``get_table_path("silver", "boundaries")``.

    Returns:
        Spark DataFrame with address columns + boundary attributes.

    See docs/entities/delta_enrichment.md for the canonical entity contract,
    constraints, and survey log.
    """
    from pyspark.sql import functions as F

    from .config import get_table_path
    from .tables import TABLES

    if addresses_table in TABLES:
        addr_path = TABLES[addresses_table]["path"]
    elif "/" in addresses_table or "://" in addresses_table:
        # Explicit raw path — has a separator or scheme. Pass through.
        addr_path = addresses_table
    else:
        # No separator AND not a registry key — almost certainly a typo'd
        # registry key (e.g. "silver.address" instead of "silver.addresses").
        # Pre-D8/SW#130 the value fell through to spark.read.load() which
        # surfaced as a confusing "path does not exist" deep in the Spark
        # stack. Fail fast at the API boundary with the available keys.
        raise ValueError(
            f"Unknown addresses_table {addresses_table!r}. Must be a key "
            f"in delta/tables.py:TABLES or a raw Delta path "
            f"(containing '/' or a scheme like 's3a://'). "
            f"Known keys: {sorted(TABLES.keys())}. (D8 / SW#130)"
        )

    addresses = (
        spark.read.format("delta").load(addr_path)
        .filter(F.col("latitude").isNotNull() & F.col("longitude").isNotNull())
    )
    addresses = addresses.selectExpr(
        "*",
        "ST_Point(CAST(longitude AS DOUBLE), CAST(latitude AS DOUBLE)) AS geom_point",
    )
    addresses.createOrReplaceTempView("addresses")

    if boundaries_path is None:
        boundaries_path = get_table_path("silver", "boundaries")

    # Pre-filter boundaries by year via DataFrame API (no SQL string
    # interpolation of `year` -- D1 / SW#123). The downstream SQL joins
    # therefore drop the redundant `b.vintage_year = {year}` predicate.
    boundaries = (
        spark.read.format("delta").load(boundaries_path)
        .filter(F.col("vintage_year") == year)
        .filter(F.col("wkt").isNotNull())
    )
    boundaries = boundaries.selectExpr(
        "*",
        "ST_GeomFromWKT(wkt) AS geom_boundary",
    )
    boundaries.createOrReplaceTempView("boundaries")

    # Three sequential LEFT JOINs. Each step's temp view carries
    # `a.geom_point` through to the next join. All three contribute to the
    # returned DataFrame (D2 / SW#124).
    enriched = spark.sql("""
        SELECT a.*, s.name AS state_name
        FROM addresses a
        LEFT JOIN boundaries s
            ON ST_Contains(s.geom_boundary, a.geom_point)
            AND s.summary_level = 'state'
    """)
    enriched.createOrReplaceTempView("with_state")

    enriched = spark.sql("""
        SELECT a.*, c.geoid AS county_geoid, c.name AS county_name
        FROM with_state a
        LEFT JOIN boundaries c
            ON ST_Contains(c.geom_boundary, a.geom_point)
            AND c.summary_level = 'county'
    """)
    enriched.createOrReplaceTempView("with_state_county")

    enriched = spark.sql("""
        SELECT a.*, d.geoid AS cd_geoid, d.name AS cd_name
        FROM with_state_county a
        LEFT JOIN boundaries d
            ON ST_Contains(d.geom_boundary, a.geom_point)
            AND d.summary_level = 'cd'
    """)

    # No .count() in the log (D3 / SW#125 -- .count() is a Spark action
    # and would force full plan execution for a log message).
    logger.info(
        "Enrichment complete: state/county/cd joins for year %d", year,
    )

    return enriched


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
