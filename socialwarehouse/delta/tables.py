"""
Delta Lake table definitions for geographic data.

Three-tier medallion architecture:
    Bronze — raw ingested data (addresses, boundary files, Census downloads)
    Silver — typed, validated, geocoded features
    Gold   — enriched with demographics, crosswalks, temporal assignments

Each table is defined as a schema + path + partitioning strategy.
"""

from pyspark.sql.types import (
    BooleanType,
    DecimalType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from .config import get_table_path


# ── Bronze schemas ───────────────────────────────────────────────────────

BRONZE_ADDRESSES = StructType([
    StructField("id", LongType(), False),
    StructField("primary_number", StringType(), True),
    StructField("street_name", StringType(), True),
    StructField("street_suffix", StringType(), True),
    StructField("city_name", StringType(), True),
    StructField("state_abbreviation", StringType(), True),
    StructField("zip5", StringType(), True),
    StructField("latitude", DecimalType(22, 16), True),
    StructField("longitude", DecimalType(22, 16), True),
    StructField("source_file", StringType(), True),
    StructField("source_row", IntegerType(), True),
    StructField("ingested_at", TimestampType(), False),
])

BRONZE_BOUNDARIES = StructType([
    StructField("geoid", StringType(), False),
    StructField("name", StringType(), True),
    StructField("summary_level", StringType(), False),
    StructField("vintage_year", IntegerType(), False),
    StructField("state_fips", StringType(), True),
    StructField("area_land", LongType(), True),
    StructField("area_water", LongType(), True),
    StructField("wkt", StringType(), True),  # WKT geometry for Sedona
    StructField("ingested_at", TimestampType(), False),
])


# ── Silver schemas ───────────────────────────────────────────────────────

SILVER_ADDRESSES = StructType([
    StructField("id", LongType(), False),
    StructField("primary_number", StringType(), True),
    StructField("street_name", StringType(), True),
    StructField("street_suffix", StringType(), True),
    StructField("city_name", StringType(), True),
    StructField("state_abbreviation", StringType(), True),
    StructField("zip5", StringType(), True),
    StructField("latitude", DoubleType(), True),
    StructField("longitude", DoubleType(), True),
    StructField("geocoded", BooleanType(), False),
    StructField("geocode_source", StringType(), True),
    StructField("geocode_quality", StringType(), True),
    StructField("geocoded_at", TimestampType(), True),
    # Census unit GEOIDs
    StructField("census_year", IntegerType(), False),
    StructField("state_geoid", StringType(), True),
    StructField("county_geoid", StringType(), True),
    StructField("tract_geoid", StringType(), True),
    StructField("block_group_geoid", StringType(), True),
    StructField("block_geoid", StringType(), True),
    StructField("vtd_geoid", StringType(), True),
    StructField("cd_geoid", StringType(), True),
    StructField("sldl_geoid", StringType(), True),
    StructField("sldu_geoid", StringType(), True),
    StructField("census_units_assigned_at", TimestampType(), True),
])

SILVER_DEMOGRAPHICS = StructType([
    StructField("geoid", StringType(), False),
    StructField("vintage_year", IntegerType(), False),
    StructField("summary_level", StringType(), False),
    StructField("variable_code", StringType(), False),
    StructField("survey_type", StringType(), False),
    StructField("estimate", DoubleType(), True),
    StructField("margin_of_error", DoubleType(), True),
])


# ── Gold schemas ─────────────────────────────────────────────────────────

GOLD_ENRICHED_ADDRESSES = StructType([
    StructField("id", LongType(), False),
    StructField("state_abbreviation", StringType(), True),
    StructField("city_name", StringType(), True),
    StructField("zip5", StringType(), True),
    StructField("latitude", DoubleType(), True),
    StructField("longitude", DoubleType(), True),
    # Census context
    StructField("census_year", IntegerType(), False),
    StructField("state_geoid", StringType(), True),
    StructField("state_name", StringType(), True),
    StructField("county_geoid", StringType(), True),
    StructField("county_name", StringType(), True),
    StructField("tract_geoid", StringType(), True),
    StructField("cd_geoid", StringType(), True),
    StructField("cd_name", StringType(), True),
    StructField("vtd_geoid", StringType(), True),
    StructField("sldl_geoid", StringType(), True),
    StructField("sldu_geoid", StringType(), True),
    # Demographics (from nearest Census survey)
    StructField("total_population", LongType(), True),
    StructField("median_household_income", DoubleType(), True),
    StructField("median_age", DoubleType(), True),
    # Urbanicity
    StructField("locale_code", IntegerType(), True),
    StructField("locale_category", StringType(), True),
])


# ── Table registry ───────────────────────────────────────────────────────

TABLES = {
    # Bronze
    "bronze.addresses": {
        "schema": BRONZE_ADDRESSES,
        "path": get_table_path("bronze", "addresses"),
        "partition_by": ["state_abbreviation"],
        "description": "Raw ingested addresses from voter files, FEC data, etc.",
    },
    "bronze.boundaries": {
        "schema": BRONZE_BOUNDARIES,
        "path": get_table_path("bronze", "boundaries"),
        "partition_by": ["summary_level", "vintage_year"],
        "description": "Raw Census TIGER/Line boundary data",
    },
    # Silver
    "silver.addresses": {
        "schema": SILVER_ADDRESSES,
        "path": get_table_path("silver", "addresses"),
        "partition_by": ["state_abbreviation", "census_year"],
        "description": "Geocoded addresses with Census unit assignments",
    },
    "silver.demographics": {
        "schema": SILVER_DEMOGRAPHICS,
        "path": get_table_path("silver", "demographics"),
        "partition_by": ["summary_level", "vintage_year"],
        "description": "Census ACS/Decennial estimates by geography",
    },
    # Gold
    "gold.enriched_addresses": {
        "schema": GOLD_ENRICHED_ADDRESSES,
        "path": get_table_path("gold", "enriched_addresses"),
        "partition_by": ["state_abbreviation", "census_year"],
        "description": "Addresses joined with boundary names, demographics, and urbanicity",
    },
}


def create_table(spark, table_name, overwrite=False):
    """Create or verify a Delta table from the registry.

    Args:
        spark: SparkSession.
        table_name: Key from TABLES registry (e.g., 'bronze.addresses').
        overwrite: If True, drop and recreate. Otherwise, create only if absent.

    Returns:
        The Delta table path.
    """
    from delta.tables import DeltaTable

    table_def = TABLES[table_name]
    path = table_def["path"]
    schema = table_def["schema"]
    partition_by = table_def.get("partition_by", [])

    if not overwrite and DeltaTable.isDeltaTable(spark, path):
        return path

    empty_df = spark.createDataFrame([], schema)
    writer = empty_df.write.format("delta")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.mode("overwrite" if overwrite else "ignore").save(path)

    return path


def create_all_tables(spark, overwrite=False):
    """Create all registered Delta tables."""
    for name in TABLES:
        create_table(spark, name, overwrite=overwrite)
    return list(TABLES.keys())
