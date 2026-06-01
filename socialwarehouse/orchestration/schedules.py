"""Dagster schedules for socialwarehouse.

One example schedule lands here: nightly refresh of the geo asset
graph (bronze observation -> silver typing -> gold enrichment ->
PostGIS materialization). Additional schedules go in this module as
they're added; instance projects override or extend by passing their
own schedules to ``Definitions(schedules=...)``.
"""

from __future__ import annotations

from dagster import AssetSelection, ScheduleDefinition, define_asset_job

from socialwarehouse.orchestration.partitions import CENSUS_VINTAGE_PARTITIONS

# Job that refreshes the entire geo domain end-to-end (silver onward;
# bronze is a SourceAsset observed via sensor).
geo_refresh_job = define_asset_job(
    name="geo_refresh",
    selection=AssetSelection.groups("silver", "gold", "postgis"),
    description="Refresh the geo asset graph from silver through PostGIS materialization.",
)

geo_nightly_schedule = ScheduleDefinition(
    job=geo_refresh_job,
    cron_schedule="0 2 * * *",  # 02:00 UTC daily
    execution_timezone="UTC",
    description="Nightly geo refresh at 02:00 UTC. Override the cron in instance projects.",
)

# Job for backfilling historical Census vintages through partitioned
# assets. Launchable via Dagit backfill dialog or CLI:
#   dagster job backfill --job geo_vintage_backfill --partitions dec_2010,acs5_2014
geo_vintage_backfill_job = define_asset_job(
    name="geo_vintage_backfill",
    selection=AssetSelection.keys(
        ["warehouse", "gold", "addresses_enriched"],
        ["postgis", "geo", "address"],
    ),
    partitions_def=CENSUS_VINTAGE_PARTITIONS,
    description="Backfill historical Census vintages through the geo gold+PostGIS pipeline.",
)


all_schedules = [geo_nightly_schedule]
all_jobs = [geo_refresh_job, geo_vintage_backfill_job]
