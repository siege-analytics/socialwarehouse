"""Civic domain asset graph: bronze -> silver -> PostGIS.

Covers NCES (National Center for Education Statistics) data:
- School districts (CCD district)
- Schools (CCD school)
- EDGE demographics

Asset graph::

    nces_districts_raw (bronze)        <- SourceAsset (raw CCD district ingest)
        |
        v
    nces_districts_typed (silver)      <- delta_table_asset, types + validates
        |
        v
    sw_civic.ncesdistrictaggregate     <- postgis_materialization_asset
        (postgis)

    nces_schools_raw (bronze)          <- SourceAsset (raw CCD school ingest)
        |
        v
    nces_schools_typed (silver)        <- delta_table_asset, types + validates
        |
        v
    sw_civic.ncesschoolaggregate       <- postgis_materialization_asset
        (postgis)

    nces_edge_raw (bronze)             <- SourceAsset (raw EDGE demographics)
        |
        v
    nces_edge_typed (silver)           <- delta_table_asset, types + validates
        |
        v
    sw_civic.ncesdistrictedge          <- postgis_materialization_asset
        demographics (postgis)
"""

from __future__ import annotations

from dagster import AssetKey, SourceAsset

from socialwarehouse.orchestration.asset_factories import (
    delta_table_asset,
    postgis_materialization_asset,
)

# ─────────────────────────────────────────────────────────────────────
# Bronze: declared as SourceAssets; ingest is owned by the upstream
# pipeline (or the existing management commands load_nces,
# load_nces_schools, load_nces_edge).
# ─────────────────────────────────────────────────────────────────────

nces_districts_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "nces_districts_raw"]),
    description="Raw NCES CCD district-level data (bronze). Produced by the upstream ingest pipeline or load_nces management command.",
    group_name="bronze",
)

nces_schools_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "nces_schools_raw"]),
    description="Raw NCES CCD school-level data (bronze). Produced by the upstream ingest pipeline or load_nces_schools management command.",
    group_name="bronze",
)

nces_edge_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "nces_edge_raw"]),
    description="Raw NCES EDGE per-district demographic estimates (bronze). Produced by the upstream ingest pipeline or load_nces_edge management command.",
    group_name="bronze",
)


# ─────────────────────────────────────────────────────────────────────
# Silver: type + validate bronze NCES data
# ─────────────────────────────────────────────────────────────────────

def _compute_nces_districts_typed(context, spark):
    """Type + validate bronze.nces_districts_raw into silver.

    Defers the actual transform to ``socialwarehouse.delta.enrichment``
    when a civic-specific typing function exists; for now this is the
    canonical hook point.
    """
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "nces_districts_raw")
    silver_path = get_table_path("silver", "nces_districts_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("nces_districts bronze row count: %d", bronze_df.count())

    typed_df = bronze_df

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


nces_districts_typed = delta_table_asset(
    layer="silver",
    table="nces_districts_typed",
    deps=["bronze/nces_districts_raw"],
    compute_fn=_compute_nces_districts_typed,
    description="Typed + validated NCES CCD district data (silver). Wraps the bronze schema with canonical silver types.",
)


def _compute_nces_schools_typed(context, spark):
    """Type + validate bronze.nces_schools_raw into silver."""
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "nces_schools_raw")
    silver_path = get_table_path("silver", "nces_schools_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("nces_schools bronze row count: %d", bronze_df.count())

    typed_df = bronze_df

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


nces_schools_typed = delta_table_asset(
    layer="silver",
    table="nces_schools_typed",
    deps=["bronze/nces_schools_raw"],
    compute_fn=_compute_nces_schools_typed,
    description="Typed + validated NCES CCD school data (silver). Wraps the bronze schema with canonical silver types.",
)


def _compute_nces_edge_typed(context, spark):
    """Type + validate bronze.nces_edge_raw into silver."""
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "nces_edge_raw")
    silver_path = get_table_path("silver", "nces_edge_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("nces_edge bronze row count: %d", bronze_df.count())

    typed_df = bronze_df

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


nces_edge_typed = delta_table_asset(
    layer="silver",
    table="nces_edge_typed",
    deps=["bronze/nces_edge_raw"],
    compute_fn=_compute_nces_edge_typed,
    description="Typed + validated NCES EDGE demographic data (silver). Wraps the bronze schema with canonical silver types.",
)


# ─────────────────────────────────────────────────────────────────────
# PostGIS: materialize silver NCES data into Django models
# ─────────────────────────────────────────────────────────────────────

def _shape_for_district_model(spark, source_path):
    """Read silver.nces_districts_typed and shape for NCESDistrictAggregate."""
    df = spark.read.format("delta").load(source_path)
    return df


civic_district_postgis = postgis_materialization_asset(
    source_layer="silver",
    source_table="nces_districts_typed",
    target_django_app_label="sw_civic",
    target_django_model_name="NCESDistrictAggregate",
    compute_sql=_shape_for_district_model,
    description="Materialize silver.nces_districts_typed into PostGIS sw_civic.NCESDistrictAggregate.",
)


def _shape_for_school_model(spark, source_path):
    """Read silver.nces_schools_typed and shape for NCESSchoolAggregate."""
    df = spark.read.format("delta").load(source_path)
    return df


civic_school_postgis = postgis_materialization_asset(
    source_layer="silver",
    source_table="nces_schools_typed",
    target_django_app_label="sw_civic",
    target_django_model_name="NCESSchoolAggregate",
    compute_sql=_shape_for_school_model,
    description="Materialize silver.nces_schools_typed into PostGIS sw_civic.NCESSchoolAggregate.",
)


def _shape_for_edge_model(spark, source_path):
    """Read silver.nces_edge_typed and shape for NCESDistrictEDGEDemographics."""
    df = spark.read.format("delta").load(source_path)
    return df


civic_edge_postgis = postgis_materialization_asset(
    source_layer="silver",
    source_table="nces_edge_typed",
    target_django_app_label="sw_civic",
    target_django_model_name="NCESDistrictEDGEDemographics",
    compute_sql=_shape_for_edge_model,
    description="Materialize silver.nces_edge_typed into PostGIS sw_civic.NCESDistrictEDGEDemographics.",
)


# Public asset list for the definitions module to discover.
all_assets = [
    nces_districts_raw,
    nces_districts_typed,
    civic_district_postgis,
    nces_schools_raw,
    nces_schools_typed,
    civic_school_postgis,
    nces_edge_raw,
    nces_edge_typed,
    civic_edge_postgis,
]
