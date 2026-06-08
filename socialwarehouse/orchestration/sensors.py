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


@sensor(
    name="replication_lag_monitor",
    description="Capture replication slot lag snapshots into sw_monitoring_replication_lag.",
    minimum_interval_seconds=60,
)
def replication_lag_sensor(context: SensorEvaluationContext) -> SensorResult:
    try:
        import django

        if not django.apps.apps.ready:
            django.setup()

        from django.conf import settings
        import psycopg2

        direct_host = getattr(settings, "POSTGRES_DIRECT_HOST", settings.DATABASES["default"]["HOST"])
        direct_port = getattr(settings, "POSTGRES_DIRECT_PORT", settings.DATABASES["default"].get("PORT", 5432))
        db = settings.DATABASES["default"]
        dsn = f"host={direct_host} port={direct_port} dbname={db['NAME']} user={db['USER']} password={db['PASSWORD']}"

        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT slot_name, "
                "pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) AS lag_bytes, "
                "EXTRACT(EPOCH FROM replay_lag) AS replay_lag_seconds "
                "FROM pg_replication_slots "
                "LEFT JOIN pg_stat_replication ON pg_replication_slots.active_pid = pg_stat_replication.pid "
                "WHERE slot_type = 'logical';"
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return SensorResult(skip_reason=SkipReason("no logical replication slots found"))

        from socialwarehouse.warehouse.models.monitoring import ReplicationLagSnapshot

        for slot_name, lag_bytes, replay_lag_seconds in rows:
            ReplicationLagSnapshot.objects.create(
                slot_name=slot_name,
                lag_bytes=lag_bytes or 0,
                replay_lag_seconds=replay_lag_seconds,
            )

        context.log.info("Recorded replication lag for %d slot(s)", len(rows))
        return SensorResult(skip_reason=SkipReason(f"recorded lag for {len(rows)} slot(s)"))

    except ImportError as exc:
        context.log.warning("replication_lag_sensor: missing dependency: %s", exc)
        return SensorResult(skip_reason=SkipReason(f"missing dependency: {exc}"))
    except Exception as exc:
        context.log.warning("replication_lag_sensor failed: %s", exc)
        return SensorResult(skip_reason=SkipReason(f"probe failed: {exc}"))


all_sensors = [bronze_addresses_sensor, replication_lag_sensor]
