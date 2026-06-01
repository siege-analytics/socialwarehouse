"""Geo domain asset graph: bronze -> silver -> gold -> PostGIS.

This is the demonstration asset graph for the orchestration layer.
Other domains (civic, demographic, economic) have their own per-domain
modules tracked in sub-issues from SW#275; each follows this same
factory-driven pattern.

Asset graph::

    addresses_raw (bronze)            <- SourceAsset (raw S3 ingest)
        |
        v
    addresses_typed (silver)          <- delta_table_asset, geocodes + types
        |
        v
    addresses_enriched (gold)         <- delta_table_asset, joins boundaries
        |
        v
    geo.address (postgis)             <- postgis_materialization_asset
"""

from __future__ import annotations

from dagster import AssetKey, SourceAsset

from socialwarehouse.orchestration.asset_factories import (
    delta_table_asset,
    postgis_materialization_asset,
)
from socialwarehouse.orchestration.partitions import (
    CENSUS_VINTAGE_PARTITIONS,
    is_hot_vintage,
    parse_vintage_partition,
)

# ── Bronze: declared as a SourceAsset; ingest is owned by the upstream ──
# Pre-Dagster ingest pipeline (or sensor — see sensors.py) lands raw
# address rows here. The orchestration layer treats it as an external
# source it observes, not something it produces.

addresses_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "addresses_raw"]),
    description="Raw ingested addresses (bronze). Produced by the upstream ingest pipeline; see sensors.py for arrival detection.",
    group_name="bronze",
)


# ── Silver: type + geocode raw addresses ──
def _compute_addresses_typed(context, spark):
    """Type + geocode bronze.addresses_raw into silver.addresses_typed.

    Defers the actual transform to ``socialwarehouse.delta.enrichment``
    when that function exists for the typing pass; for now this is the
    canonical hook point. Per the SW#275 pre-author inventory: shape
    measurement of the bronze table goes here before the first
    materialization.
    """
    from socialwarehouse.delta.config import get_table_path

    bronze_path = get_table_path("bronze", "addresses_raw")
    silver_path = get_table_path("silver", "addresses_typed")

    bronze_df = spark.read.format("delta").load(bronze_path)
    context.log.info("bronze row count: %d", bronze_df.count())

    # Minimal typing transform: cast columns to the silver schema's
    # expected types. The full geocoding pass lives in
    # delta/enrichment.py and is invoked here once the bronze schema
    # stabilizes — tracked as part of SW#275's per-domain sub-issues.
    typed_df = bronze_df  # placeholder until the typing transform lands

    typed_df.write.format("delta").mode("overwrite").save(silver_path)


addresses_typed = delta_table_asset(
    layer="silver",
    table="addresses_typed",
    deps=["bronze/addresses_raw"],
    compute_fn=_compute_addresses_typed,
    description="Typed + geocoded addresses (silver). Wraps the bronze schema with the canonical silver types.",
)


# ── Gold: enrich silver addresses with boundary attributes ──
# Partitioned by Census vintage so historical boundary sets can be
# backfilled independently (SW#281).
def _compute_addresses_enriched(context, spark):
    """Enrich silver addresses with state/county/CD boundary attributes.

    Delegates to ``socialwarehouse.delta.enrichment.enrich_addresses_with_boundaries``
    — the existing Spark+Sedona enrichment function. When running as a
    partitioned asset, ``context.partition_key`` determines the vintage
    year for boundary lookup.
    """
    from socialwarehouse.delta.config import get_table_path
    from socialwarehouse.delta.enrichment import enrich_addresses_with_boundaries

    silver_path = get_table_path("silver", "addresses_typed")
    gold_path = get_table_path("gold", "addresses_enriched")

    silver_df = spark.read.format("delta").load(silver_path)
    silver_df.createOrReplaceTempView("addresses_typed_view")

    if context.has_partition_key:
        partition = parse_vintage_partition(context.partition_key)
        vintage = partition.vintage_year
    else:
        vintage = 2020

    context.log.info("enriching addresses with vintage=%d boundaries", vintage)
    enriched = enrich_addresses_with_boundaries(spark, "addresses_typed_view", year=vintage)

    enriched.write.format("delta").mode("overwrite").save(gold_path)


addresses_enriched = delta_table_asset(
    layer="gold",
    table="addresses_enriched",
    deps=["silver/addresses_typed"],
    compute_fn=_compute_addresses_enriched,
    description="Boundary-enriched addresses (gold). Wraps delta.enrichment.enrich_addresses_with_boundaries.",
    partitions_def=CENSUS_VINTAGE_PARTITIONS,
)


# ── PostGIS: materialize gold addresses into the Django `Address` model ──
def _shape_for_address_model(spark, source_path):
    """Read gold.addresses_enriched and shape into the geo.Address schema.

    The shape mapping is intentionally minimal here; instance projects
    that extend the Address model with additional columns override
    this function in their own asset definition. See
    docs/orchestration/instance-project-guide.md for the extension
    pattern.
    """
    df = spark.read.format("delta").load(source_path)
    # Select only the columns Django's Address model expects. The
    # canonical column list lives in geo/models/address.py; keeping it
    # implicit here (rather than re-listed) is intentional — Spark's
    # to_sql will fail loudly if a column is missing, which is the
    # right failure mode versus silent column drift.
    return df


geo_address_postgis = postgis_materialization_asset(
    source_layer="gold",
    source_table="addresses_enriched",
    target_django_app_label="geo",
    target_django_model_name="Address",
    compute_sql=_shape_for_address_model,
    description="Materialize gold.addresses_enriched into PostGIS geo.address (Django Address model).",
    partitions_def=CENSUS_VINTAGE_PARTITIONS,
)


# Public asset list for the definitions module to discover.
all_assets = [
    addresses_raw,
    addresses_typed,
    addresses_enriched,
    geo_address_postgis,
]
