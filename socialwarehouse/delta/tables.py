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
    DateType,
    DecimalType,
    DoubleType,
    IntegerType,
    LongType,
    MapType,
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

## Per-vendor voter-file bronze (SW#251).
##
## Bronze stores the full vendor row as JSON in the `raw` column. The
## four supported vendors (PDI, L2, Catalist, TargetSmart) have
## hundreds of mostly-non-overlapping columns each — a union'd table
## would be 1000+ nullable columns with poor column-prune behavior.
## Per-vendor bronze keeps each importer schema close to its native
## shape. Silver does the canonical unification.
##
## Schema-evolution: bronze is JSON-stringified, so vendor-side
## column changes do not require bronze schema migrations. Bronze
## evolution is restricted to the metadata fields below.
_BRONZE_VOTER_FILE_FIELDS = [
    StructField("vendor_voter_id", StringType(), False),
    StructField("state_abbreviation", StringType(), False),
    StructField("raw", StringType(), False),
    StructField("source_file", StringType(), True),
    StructField("source_row", LongType(), True),
    StructField("ingested_at", TimestampType(), False),
]

BRONZE_VOTER_FILE_TS = StructType(_BRONZE_VOTER_FILE_FIELDS)
BRONZE_VOTER_FILE_L2 = StructType(_BRONZE_VOTER_FILE_FIELDS)
BRONZE_VOTER_FILE_CATALIST = StructType(_BRONZE_VOTER_FILE_FIELDS)
BRONZE_VOTER_FILE_PDI = StructType(_BRONZE_VOTER_FILE_FIELDS)


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

# Intentionally NOT SCD2: the warehouse-side DimGeography tracks
# is_current / effective_from / effective_to because geographies are
# revised within a vintage (TIGER/Line corrections, redistricting
# revisions). Census demographic estimates, by contrast, are
# point-in-time snapshots keyed by the composite
# (geoid, vintage_year, summary_level, variable_code, survey_type).
# Revisions are published as a NEW vintage_year or survey_type — never
# as an in-place edit of the same key. The natural key is the version,
# so SCD2 effective_from/to would be redundant tracking.
# Re-loads of the same key upsert by primary key.
# (D7 / SW#129 — intentional simplification, documented per ticket.)
SILVER_DEMOGRAPHICS = StructType([
    StructField("geoid", StringType(), False),
    StructField("vintage_year", IntegerType(), False),
    StructField("summary_level", StringType(), False),
    StructField("variable_code", StringType(), False),
    StructField("survey_type", StringType(), False),
    StructField("estimate", DoubleType(), True),
    StructField("margin_of_error", DoubleType(), True),
])


## Silver Person / score / vote-history (SW#251).
##
## Canonical, typed, vendor-neutral. One row per (vendor, vendor_voter_id):
## same physical voter from two vendors yields two silver rows. Cross-
## vendor probabilistic matching is a follow-on; the schema permits it
## without rewrites by adding a `canonical_person_id` column later.
##
## `vendor_extras` Map<String, String> holds vendor-divergent fields
## that have not been promoted to canonical columns. See
## docs/warehouse-schema-evolution.md for the promotion playbook.

SILVER_PERSONS = StructType([
    # Natural key
    StructField("vendor", StringType(), False),
    StructField("vendor_voter_id", StringType(), False),
    StructField("person_key", StringType(), False),
    # Identity
    StructField("first_name", StringType(), True),
    StructField("middle_name", StringType(), True),
    StructField("last_name", StringType(), True),
    StructField("name_suffix", StringType(), True),
    StructField("dob", DateType(), True),
    StructField("gender", StringType(), True),
    StructField("ethnicity", StringType(), True),
    StructField("language", StringType(), True),
    # Registration
    StructField("registration_status", StringType(), True),
    StructField("registration_state", StringType(), False),
    StructField("registration_date", DateType(), True),
    StructField("party_registration", StringType(), True),
    StructField("voter_status_reason", StringType(), True),
    # Address (resolved to canonical via geo pipeline)
    StructField("address_id", LongType(), True),
    StructField("address_line1", StringType(), True),
    StructField("address_line2", StringType(), True),
    StructField("city", StringType(), True),
    StructField("zip5", StringType(), True),
    StructField("zip4", StringType(), True),
    StructField("latitude", DoubleType(), True),
    StructField("longitude", DoubleType(), True),
    # Pre-joined geoids (vendor pre-joins trusted on ingest; refreshed
    # on redistricting-plan change)
    StructField("census_year", IntegerType(), True),
    StructField("state_geoid", StringType(), True),
    StructField("county_geoid", StringType(), True),
    StructField("tract_geoid", StringType(), True),
    StructField("block_group_geoid", StringType(), True),
    StructField("vtd_geoid", StringType(), True),
    StructField("cd_geoid", StringType(), True),
    StructField("sldl_geoid", StringType(), True),
    StructField("sldu_geoid", StringType(), True),
    StructField("zcta_geoid", StringType(), True),
    # Household
    StructField("household_id", StringType(), True),
    StructField("household_size", IntegerType(), True),
    StructField("is_head_of_household", BooleanType(), True),
    # Vote-history aggregates (computed by silver build from
    # silver.vote_history; denormalized for query speed)
    StructField("general_election_count", IntegerType(), True),
    StructField("primary_election_count", IntegerType(), True),
    StructField("total_vote_count", IntegerType(), True),
    StructField("last_voted_at", DateType(), True),
    StructField("vote_frequency_category", StringType(), True),
    # Evolvable vendor extension bag (see schema-evolution doc)
    StructField("vendor_extras", MapType(StringType(), StringType()), True),
    # Ontology mixin fields (A-1 / #286)
    StructField("entity_uuid", StringType(), True),
    StructField("data_source", StringType(), True),
    StructField("jurisdiction_level", StringType(), True),
    StructField("source_record_id", StringType(), True),
    # Provenance
    StructField("source_file", StringType(), True),
    StructField("ingested_at", TimestampType(), False),
    StructField("silver_built_at", TimestampType(), False),
])


SILVER_PERSON_SCORES = StructType([
    StructField("person_key", StringType(), False),
    StructField("score_type", StringType(), False),
    StructField("value", DoubleType(), False),
    StructField("source_vendor", StringType(), False),
    StructField("methodology_version", StringType(), False),
    StructField("scored_at", TimestampType(), True),
    StructField("loaded_at", TimestampType(), False),
])


SILVER_VOTE_HISTORY = StructType([
    StructField("person_key", StringType(), False),
    StructField("election_date", DateType(), False),
    StructField("election_year", IntegerType(), False),
    StructField("election_type", StringType(), False),
    StructField("voted_method", StringType(), True),
    StructField("source_vendor", StringType(), False),
    StructField("loaded_at", TimestampType(), False),
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


# ── Core schemas (cross-source entity resolution) ───────────────────────

SILVER_ENTITY_IDENTIFIERS = StructType([
    StructField("entity_uuid", StringType(), False),
    StructField("identifier_type", StringType(), False),
    StructField("identifier_value", StringType(), False),
    StructField("data_source", StringType(), False),
    StructField("jurisdiction_level", StringType(), True),
    StructField("jurisdiction_state", StringType(), True),
    StructField("normalizer_version", IntegerType(), False),
    StructField("valid_from", TimestampType(), False),
    StructField("valid_to", TimestampType(), True),
    StructField("ingested_at", TimestampType(), False),
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
    "bronze.voter_file_ts": {
        "schema": BRONZE_VOTER_FILE_TS,
        "path": get_table_path("bronze", "voter_file_ts"),
        "partition_by": ["state_abbreviation"],
        "description": "Raw TargetSmart voter-file rows (JSON-stringified)",
    },
    "bronze.voter_file_l2": {
        "schema": BRONZE_VOTER_FILE_L2,
        "path": get_table_path("bronze", "voter_file_l2"),
        "partition_by": ["state_abbreviation"],
        "description": "Raw L2 voter-file rows (JSON-stringified)",
    },
    "bronze.voter_file_catalist": {
        "schema": BRONZE_VOTER_FILE_CATALIST,
        "path": get_table_path("bronze", "voter_file_catalist"),
        "partition_by": ["state_abbreviation"],
        "description": "Raw Catalist voter-file rows (JSON-stringified)",
    },
    "bronze.voter_file_pdi": {
        "schema": BRONZE_VOTER_FILE_PDI,
        "path": get_table_path("bronze", "voter_file_pdi"),
        "partition_by": ["state_abbreviation"],
        "description": "Raw PDI voter-file rows (JSON-stringified)",
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
    "silver.persons": {
        "schema": SILVER_PERSONS,
        "path": get_table_path("silver", "persons"),
        "partition_by": ["registration_state", "vendor"],
        "description": "Canonical voter records, vendor-neutral, address-resolved",
    },
    "silver.person_scores": {
        "schema": SILVER_PERSON_SCORES,
        "path": get_table_path("silver", "person_scores"),
        "partition_by": ["source_vendor", "score_type"],
        "description": "Temporal-versioned scores per person, source-vendor-tagged",
    },
    "silver.vote_history": {
        "schema": SILVER_VOTE_HISTORY,
        "path": get_table_path("silver", "vote_history"),
        "partition_by": ["election_year", "source_vendor"],
        "description": "Per-person per-election vote events",
    },
    # Core (cross-source entity resolution)
    "silver.entity_identifiers": {
        "schema": SILVER_ENTITY_IDENTIFIERS,
        "path": get_table_path("silver", "entity_identifiers"),
        "partition_by": ["data_source"],
        "description": "Cross-source entity identifier log for resolution",
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
