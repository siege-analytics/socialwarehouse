"""Dagster schedules for socialwarehouse.

One example schedule lands here: nightly refresh of the geo asset
graph (bronze observation -> silver typing -> gold enrichment ->
PostGIS materialization). Additional schedules go in this module as
they're added; instance projects override or extend by passing their
own schedules to ``Definitions(schedules=...)``.
"""

from __future__ import annotations

from dagster import AssetSelection, ScheduleDefinition, define_asset_job

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


all_schedules = [geo_nightly_schedule]
all_jobs = [geo_refresh_job]
