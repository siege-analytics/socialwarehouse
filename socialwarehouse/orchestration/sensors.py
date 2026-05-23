"""Dagster sensors for socialwarehouse.

One example sensor lands here: detect new arrivals in the bronze
addresses_raw Delta table (commit timestamp moved forward since the
last successful run). When fires, it requests materialization of the
downstream silver/gold/postgis assets.

Instance projects add more sensors per their ingest patterns (S3
prefix arrivals, Kafka offsets, external job completions, etc.).
"""

from __future__ import annotations

from dagster import (
    AssetKey,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    sensor,
)

from socialwarehouse.orchestration.schedules import geo_refresh_job

BRONZE_ADDRESSES_KEY = AssetKey(["warehouse", "bronze", "addresses_raw"])


@sensor(
    job=geo_refresh_job,
    name="bronze_addresses_arrival",
    description="Trigger geo_refresh when bronze.addresses_raw has new data since the last run.",
    minimum_interval_seconds=300,  # check every 5 minutes
)
def bronze_addresses_sensor(context: SensorEvaluationContext) -> SensorResult:
    """Sensor: kick geo_refresh when bronze.addresses_raw Delta table commits.

    Uses Dagster's asset-observation cursor: tracks the last seen
    commit timestamp on the bronze Delta table. When the live table's
    latest commit is newer than the cursor, request a run and advance
    the cursor.

    This is the example pattern — instance projects clone this sensor
    for their own bronze ingests, parameterizing the Delta path + the
    downstream job.
    """
    from socialwarehouse.delta.config import get_spark_session, get_table_path

    bronze_path = get_table_path("bronze", "addresses_raw")

    try:
        spark = get_spark_session(app_name="dagster-sensor", enable_sedona=False)
        history = spark.sql(f"DESCRIBE HISTORY delta.`{bronze_path}` LIMIT 1").collect()
        if not history:
            return SensorResult(skip_reason=SkipReason("bronze.addresses_raw has no commits yet"))
        latest_ts = str(history[0]["timestamp"])
    except Exception as exc:
        # Sensor failures should not crash the daemon; log + skip.
        context.log.warning("bronze_addresses_sensor probe failed: %s", exc)
        return SensorResult(skip_reason=SkipReason(f"probe failed: {exc}"))

    if context.cursor == latest_ts:
        return SensorResult(skip_reason=SkipReason(f"no new commits since {latest_ts}"))

    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f"bronze_addresses_{latest_ts}",
                tags={"trigger": "bronze_addresses_arrival", "delta_commit_ts": latest_ts},
            )
        ],
        cursor=latest_ts,
    )


all_sensors = [bronze_addresses_sensor]
