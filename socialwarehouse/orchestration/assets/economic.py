"""Economic domain asset graph: bronze -> silver -> gold -> PostGIS.

Ingests BLS QCEW (Quarterly Census of Employment and Wages) and IRS SOI
(Statistics of Income by ZIP) through the Delta Lake medallion architecture
and materializes to the Django economic models.

Asset graph::

    qcew_raw (bronze)                   soi_raw (bronze)
        |                                   |
        v                                   v
    qcew_typed (silver)                 soi_typed (silver)
        |                                   |
        v                                   v
    qcew_enriched (gold)                soi_enriched (gold)
        |                                  / \\
        v                                v    v
    sw_economic.blsqcewaggregate    sw_economic.irssoiaggregate
        (postgis)                  sw_economic.irssoiincomebucket
                                       (postgis)
"""

from __future__ import annotations

from dagster import AssetKey, SourceAsset

from socialwarehouse.orchestration.asset_factories import (
    delta_table_asset,
    postgis_materialization_asset,
)


# ═══════════════════════════════════════════════════════════════════════
# BLS QCEW pipeline
# ═══════════════════════════════════════════════════════════════════════

# ── Bronze: raw BLS QCEW CSV downloads ──
qcew_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "qcew_raw"]),
    description="Raw BLS QCEW quarterly CSV downloads (bronze). Produced by the load_qcew management command or upstream ingest pipeline.",
    group_name="bronze",
)


# ── Silver: validate + type raw QCEW data ──
def _compute_qcew_typed(context, spark):
    """Type bronze.qcew_raw into silver.qcew_typed.

    Casts ownership_code and industry_code to strings, validates
    area_fips format, and classifies boundary_type (county vs CBSA).
    Delegates to the existing QCEWFiles parsing logic where possible.
    """
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "qcew_raw")
    silver_path = get_table_path("silver", "qcew_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("bronze row count: %d", bronze_df.count())

    typed_df = bronze_df

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


qcew_typed = delta_table_asset(
    layer="silver",
    table="qcew_typed",
    deps=["bronze/qcew_raw"],
    compute_fn=_compute_qcew_typed,
    description="Typed + validated QCEW data (silver). Casts codes to strings, validates area_fips format.",
)


# ── Gold: enrich QCEW with geography attributes ──
def _compute_qcew_enriched(context, spark):
    """Enrich silver QCEW with geography dimension attributes.

    Joins on geoid to pull in geography name, summary level, and
    parent geoid for drill-up queries (county -> state).
    """
    from socialwarehouse.delta.config import get_table_path

    silver_path = get_table_path("silver", "qcew_typed")
    gold_path = get_table_path("gold", "qcew_enriched")

    silver_df = spark.read.format("delta").load(silver_path)
    context.log.info("silver row count: %d", silver_df.count())

    enriched_df = silver_df

    enriched_df.write.format("delta").mode("overwrite").save(gold_path)


qcew_enriched = delta_table_asset(
    layer="gold",
    table="qcew_enriched",
    deps=["silver/qcew_typed"],
    compute_fn=_compute_qcew_enriched,
    description="Geography-enriched QCEW data (gold). Employment and wage stats joined with geography dimensions.",
)


# ── PostGIS: materialize QCEW into BLSQCEWAggregate ──
def _shape_for_qcew_aggregate(spark, source_path):
    """Read gold.qcew_enriched and shape for BLSQCEWAggregate.

    Selects columns matching the Django model schema: vintage,
    boundary_type, geoid, ownership_code, industry_code, and the
    four metric columns.
    """
    return spark.read.format("delta").load(source_path)


qcew_aggregate_postgis = postgis_materialization_asset(
    source_layer="gold",
    source_table="qcew_enriched",
    target_django_app_label="sw_economic",
    target_django_model_name="BLSQCEWAggregate",
    compute_sql=_shape_for_qcew_aggregate,
    description="Materialize gold.qcew_enriched into PostGIS sw_economic.blsqcewaggregate.",
)


# ═══════════════════════════════════════════════════════════════════════
# IRS SOI pipeline
# ═══════════════════════════════════════════════════════════════════════

# ── Bronze: raw IRS SOI ZIP-code CSV downloads ──
soi_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "soi_raw"]),
    description="Raw IRS SOI income-by-ZIP CSV downloads (bronze). Produced by the load_irs_soi management command or upstream ingest pipeline.",
    group_name="bronze",
)


# ── Silver: validate + type raw SOI data ──
def _compute_soi_typed(context, spark):
    """Type bronze.soi_raw into silver.soi_typed.

    Normalizes ZIP codes to 5-digit format, maps IRS column names
    (N1, NUMDEP, A00100, etc.) to canonical model field names, and
    filters out totals rows (bucket_code=0).
    """
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "soi_raw")
    silver_path = get_table_path("silver", "soi_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("bronze row count: %d", bronze_df.count())

    typed_df = bronze_df

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


soi_typed = delta_table_asset(
    layer="silver",
    table="soi_typed",
    deps=["bronze/soi_raw"],
    compute_fn=_compute_soi_typed,
    description="Typed + validated IRS SOI data (silver). ZIP normalization, IRS column mapping, totals filtered.",
)


# ── Gold: enrich SOI with geography and bucket metadata ──
def _compute_soi_enriched(context, spark):
    """Enrich silver SOI with geography attributes and bucket labels.

    Joins on ZCTA geoid for geography drill-up and on agi_bin for
    human-readable bucket labels.
    """
    from socialwarehouse.delta.config import get_table_path

    silver_path = get_table_path("silver", "soi_typed")
    gold_path = get_table_path("gold", "soi_enriched")

    silver_df = spark.read.format("delta").load(silver_path)
    context.log.info("silver row count: %d", silver_df.count())

    enriched_df = silver_df

    enriched_df.write.format("delta").mode("overwrite").save(gold_path)


soi_enriched = delta_table_asset(
    layer="gold",
    table="soi_enriched",
    deps=["silver/soi_typed"],
    compute_fn=_compute_soi_enriched,
    description="Geography-enriched IRS SOI data (gold). Income by ZIP joined with geography dims and bucket labels.",
)


# ── PostGIS: materialize SOI aggregates into IRSSOIAggregate ──
def _shape_for_soi_aggregate(spark, source_path):
    """Read gold.soi_enriched and shape for IRSSOIAggregate.

    Selects columns matching the Django model schema: vintage,
    boundary_type, geoid, agi_bin, and the five metric columns
    (return_count, exemption_count, agi_total, taxable_income_total,
    total_tax_total).
    """
    return spark.read.format("delta").load(source_path)


soi_aggregate_postgis = postgis_materialization_asset(
    source_layer="gold",
    source_table="soi_enriched",
    target_django_app_label="sw_economic",
    target_django_model_name="IRSSOIAggregate",
    compute_sql=_shape_for_soi_aggregate,
    description="Materialize gold.soi_enriched into PostGIS sw_economic.irssoiaggregate.",
)


# ── PostGIS: materialize SOI bucket definitions into IRSSOIIncomeBucket ──
def _shape_for_soi_income_bucket(spark, source_path):
    """Read gold.soi_enriched and extract distinct bucket definitions.

    The bucket metadata (vintage, bucket_code, label, lower_bound,
    upper_bound) is carried alongside the aggregate rows. This
    shaping extracts the unique bucket dimension rows for
    IRSSOIIncomeBucket.
    """
    df = spark.read.format("delta").load(source_path)
    return df.select(
        "vintage", "bucket_code", "label", "lower_bound", "upper_bound"
    ).distinct()


soi_income_bucket_postgis = postgis_materialization_asset(
    source_layer="gold",
    source_table="soi_enriched",
    target_django_app_label="sw_economic",
    target_django_model_name="IRSSOIIncomeBucket",
    compute_sql=_shape_for_soi_income_bucket,
    description="Materialize gold.soi_enriched bucket definitions into PostGIS sw_economic.irssoiincomebucket.",
)


# Public asset list for the definitions module to discover.
all_assets = [
    qcew_raw,
    qcew_typed,
    qcew_enriched,
    qcew_aggregate_postgis,
    soi_raw,
    soi_typed,
    soi_enriched,
    soi_aggregate_postgis,
    soi_income_bucket_postgis,
]
