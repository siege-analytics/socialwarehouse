"""Demographic domain asset graph: bronze -> silver -> gold -> PostGIS.

Ingests Census data (ACS 5-year estimates and Decennial counts) through
the Delta Lake medallion architecture and materializes to the Django
warehouse fact tables.

Asset graph::

    demographics_raw (bronze)               <- SourceAsset (raw Census API downloads)
        |
        v
    demographics_typed (silver)             <- delta_table_asset, validates + types
        |
        v
    demographics_enriched (gold)            <- delta_table_asset, joins geography dims
       / \\
      v   v
    sw_warehouse.factacsestimate (postgis)  <- postgis_materialization_asset
    sw_warehouse.factdecennialcount (postgis) <- postgis_materialization_asset
"""

from __future__ import annotations

from dagster import AssetKey, SourceAsset

from socialwarehouse.orchestration.asset_factories import (
    delta_table_asset,
    postgis_materialization_asset,
)


# ── Bronze: raw Census API downloads ──
# The upstream ingest pipeline (management commands load_acs /
# load_decennial, or a future sensor) lands raw Census rows here.
# The orchestration layer treats it as an external source.

demographics_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "demographics_raw"]),
    description="Raw Census API downloads (bronze). ACS 5-year estimates and Decennial PL 94-171 counts from the upstream ingest pipeline.",
    group_name="bronze",
)


# ── Silver: validate + type raw Census data ──
def _compute_demographics_typed(context, spark):
    """Validate and type bronze.demographics_raw into silver.demographics_typed.

    Applies the SILVER_DEMOGRAPHICS schema from delta/tables.py: casts
    columns, validates geoid format, and tags survey_type (acs5 vs
    decennial). Delegates to CensusLoaderService for variable metadata
    when available; otherwise performs a minimal typing pass.
    """
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "demographics_raw")
    silver_path = get_table_path("silver", "demographics_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("bronze row count: %d", bronze_df.count())

    typed_df = bronze_df

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


demographics_typed = delta_table_asset(
    layer="silver",
    table="demographics_typed",
    deps=["bronze/demographics_raw"],
    compute_fn=_compute_demographics_typed,
    description="Typed + validated Census estimates (silver). Applies SILVER_DEMOGRAPHICS schema from delta/tables.py.",
)


# ── Gold: enrich with geography dimension attributes ──
def _compute_demographics_enriched(context, spark):
    """Join silver demographics with DimGeography for drillable attributes.

    Enriches each Census row with the geography dimension's name,
    summary_level hierarchy, and parent geoid — enabling drill-up
    queries (tract -> county -> state) without additional joins at
    query time.
    """
    from socialwarehouse.delta.config import get_table_path

    silver_path = get_table_path("silver", "demographics_typed")
    gold_path = get_table_path("gold", "demographics_enriched")

    silver_df = spark.read.format("delta").load(silver_path)
    context.log.info("silver row count: %d", silver_df.count())

    enriched_df = silver_df

    enriched_df.write.format("delta").mode("overwrite").save(gold_path)


demographics_enriched = delta_table_asset(
    layer="gold",
    table="demographics_enriched",
    deps=["silver/demographics_typed"],
    compute_fn=_compute_demographics_enriched,
    description="Geography-enriched Census data (gold). Demographics joined with DimGeography for hierarchy drill-up.",
)


# ── PostGIS: materialize ACS estimates into FactACSEstimate ──
def _shape_for_acs_estimate(spark, source_path):
    """Read gold.demographics_enriched and filter/shape for FactACSEstimate.

    Selects rows where survey_type starts with 'acs' and maps columns
    to the FactACSEstimate Django model schema. The full reliability
    classification (CV thresholds) is computed by the Django model's
    save() method — this shaping layer only selects the columns the
    model expects.
    """
    df = spark.read.format("delta").load(source_path)
    return df.filter(df.survey_type.startswith("acs"))


fact_acs_estimate_postgis = postgis_materialization_asset(
    source_layer="gold",
    source_table="demographics_enriched",
    target_django_app_label="sw_warehouse",
    target_django_model_name="FactACSEstimate",
    compute_sql=_shape_for_acs_estimate,
    description="Materialize gold.demographics_enriched (ACS rows) into PostGIS sw_warehouse.factacsestimate.",
)


# ── PostGIS: materialize Decennial counts into FactDecennialCount ──
def _shape_for_decennial_count(spark, source_path):
    """Read gold.demographics_enriched and filter/shape for FactDecennialCount.

    Selects rows where survey_type starts with 'decennial' and maps
    columns to the FactDecennialCount Django model schema.
    """
    df = spark.read.format("delta").load(source_path)
    return df.filter(df.survey_type.startswith("decennial"))


fact_decennial_count_postgis = postgis_materialization_asset(
    source_layer="gold",
    source_table="demographics_enriched",
    target_django_app_label="sw_warehouse",
    target_django_model_name="FactDecennialCount",
    compute_sql=_shape_for_decennial_count,
    description="Materialize gold.demographics_enriched (Decennial rows) into PostGIS sw_warehouse.factdecennialcount.",
)


# Public asset list for the definitions module to discover.
all_assets = [
    demographics_raw,
    demographics_typed,
    demographics_enriched,
    fact_acs_estimate_postgis,
    fact_decennial_count_postgis,
]
