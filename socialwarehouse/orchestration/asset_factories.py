"""Reusable Dagster asset factories for socialwarehouse.

The factories produce ``AssetsDefinition`` objects whose keys derive
from ``socialwarehouse.delta.config.get_table_path()`` so the asset
graph and the on-disk Delta layout stay coupled by construction.

Instance projects use these factories to register their own assets
without copying the wiring boilerplate:

.. code-block:: python

    from socialwarehouse.orchestration.asset_factories import (
        delta_table_asset,
        postgis_materialization_asset,
    )
    from socialwarehouse.delta import tables as t

    addresses_silver = delta_table_asset(
        layer="silver",
        table="addresses_typed",
        deps=["bronze/addresses_raw"],
        compute_fn=lambda spark, ctx: spark.sql(...)
    )
"""

from __future__ import annotations

import io
import time
from typing import Callable, Iterable, Optional

from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    AssetKey,
    MaterializeResult,
    PartitionsDefinition,
    asset,
)


def _key_for(layer: str, table: str) -> AssetKey:
    """Asset key = ('warehouse', '<layer>', '<table>'); mirrors Delta layout."""
    return AssetKey(["warehouse", layer, table])


def delta_table_asset(
    *,
    layer: str,
    table: str,
    deps: Optional[Iterable[str]] = None,
    compute_fn: Callable[[AssetExecutionContext, "SparkSession"], None],  # noqa: F821
    description: Optional[str] = None,
    group_name: Optional[str] = None,
    partitions_def: Optional[PartitionsDefinition] = None,
) -> AssetsDefinition:
    """Factory: build a Dagster asset that materializes a Delta table.

    ``compute_fn`` receives the asset context and a live SparkSession
    (from ``SparkResource``) and is responsible for writing the Delta
    table at ``get_table_path(layer, table)``. The factory handles
    asset-key derivation, dep wiring, and result reporting.

    Args:
        layer: 'bronze' | 'silver' | 'gold'
        table: table name within the layer (matches delta/tables.py)
        deps: list of dep strings like 'bronze/addresses_raw' that
              resolve to AssetKey(['warehouse', 'bronze', 'addresses_raw'])
        compute_fn: callable(context, spark) -> None that writes the Delta table
        description: optional human-readable description (defaults to a stock string)
        group_name: optional Dagster group (defaults to the layer)
        partitions_def: optional PartitionsDefinition for vintage backfill support;
            when provided, compute_fn receives context.partition_key
    """
    from socialwarehouse.delta.config import get_table_path
    from socialwarehouse.orchestration.resources import SparkResource

    dep_keys = []
    for d in deps or []:
        dep_layer, dep_table = d.split("/", 1)
        dep_keys.append(_key_for(dep_layer, dep_table))

    @asset(
        key=_key_for(layer, table),
        deps=dep_keys,
        description=description or f"Delta table {layer}.{table} (path: {get_table_path(layer, table)})",
        group_name=group_name or layer,
        required_resource_keys={"spark"},
        partitions_def=partitions_def,
    )
    def _delta_asset(context: AssetExecutionContext) -> MaterializeResult:
        spark_resource: SparkResource = getattr(context.resources, "spark")
        with spark_resource.session(context) as spark:
            compute_fn(context, spark)
        table_path = get_table_path(layer, table)
        # Read back row count for the materialization metadata; cheap when
        # the table is freshly written. If this becomes load-bearing on
        # large tables, swap for an estimate or skip.
        row_count = spark.read.format("delta").load(table_path).count()
        return MaterializeResult(
            metadata={
                "path": table_path,
                "row_count": row_count,
                "layer": layer,
            }
        )

    return _delta_asset


def _copy_to_postgis(pdf, table_name: str, postgis_resource) -> None:
    """Bulk-load a DataFrame into PostGIS via COPY FROM STDIN.

    Uses psycopg2's ``copy_expert`` through the raw connection exposed
    by ``PostGISResource``. The DataFrame is serialized to CSV in memory.
    """
    columns = ", ".join(f'"{col}"' for col in pdf.columns)
    copy_sql = f'COPY "{table_name}" ({columns}) FROM STDIN WITH CSV HEADER'

    buf = io.StringIO()
    pdf.to_csv(buf, index=False, header=True)
    buf.seek(0)

    with postgis_resource.raw_connection() as conn:
        with conn.cursor() as cur:
            cur.copy_expert(copy_sql, buf)
        conn.commit()


def postgis_materialization_asset(
    *,
    source_layer: str,
    source_table: str,
    target_django_app_label: str,
    target_django_model_name: str,
    compute_sql: Callable[["SparkSession", str], "DataFrame"],  # noqa: F821
    copy_threshold: int = 100_000,
    description: Optional[str] = None,
    group_name: str = "postgis",
    partitions_def: Optional[PartitionsDefinition] = None,
) -> AssetsDefinition:
    """Factory: build a Dagster asset that materializes a Delta table into PostGIS.

    The flow: read the source Delta table, run ``compute_sql`` to shape
    it into the target schema, write to PostGIS via SQLAlchemy
    ``to_sql`` for small loads or PostgreSQL ``COPY`` for loads above
    ``copy_threshold`` rows.

    ``compute_sql(spark, source_path)`` is called with the SparkSession
    and the source Delta path; it returns the DataFrame to write to
    PostGIS. The target table is computed from the Django model's
    ``_meta.db_table``.

    Args:
        source_layer: 'silver' | 'gold' (bronze rarely materializes to PostGIS)
        source_table: source table name in the Delta layer
        target_django_app_label: e.g. 'geo'
        target_django_model_name: e.g. 'Address'
        compute_sql: callable(spark, source_path) -> DataFrame (shape for PostGIS)
        copy_threshold: row count above which COPY is used instead of to_sql (default 100K)
        description: optional override
        group_name: Dagster group name (default 'postgis')
        partitions_def: optional PartitionsDefinition for vintage backfill support;
            when provided, compute_sql receives context.partition_key via the context
    """
    from socialwarehouse.delta.config import get_table_path
    from socialwarehouse.orchestration.resources import PostGISResource, SparkResource

    @asset(
        key=AssetKey(["postgis", target_django_app_label, target_django_model_name.lower()]),
        deps=[_key_for(source_layer, source_table)],
        description=description
        or f"PostGIS materialization: {source_layer}.{source_table} -> {target_django_app_label}.{target_django_model_name}",
        group_name=group_name,
        required_resource_keys={"spark", "postgis"},
        partitions_def=partitions_def,
    )
    def _postgis_asset(context: AssetExecutionContext) -> MaterializeResult:
        spark_resource: SparkResource = getattr(context.resources, "spark")
        postgis_resource: PostGISResource = getattr(context.resources, "postgis")

        source_path = get_table_path(source_layer, source_table)
        t_start = time.monotonic()

        with spark_resource.session(context) as spark:
            df = compute_sql(spark, source_path)
            t_spark = time.monotonic()

            pdf = df.toPandas()
            t_pandas = time.monotonic()

        row_count = len(pdf)
        django_model = _resolve_django_model(target_django_app_label, target_django_model_name)
        table_name = django_model._meta.db_table

        use_copy = row_count > copy_threshold
        write_method = "copy" if use_copy else "to_sql"
        context.log.info(
            "PostGIS write: %d rows via %s (threshold=%d) -> %s",
            row_count, write_method, copy_threshold, table_name,
        )

        try:
            if use_copy:
                _copy_to_postgis(pdf, table_name, postgis_resource)
            else:
                with postgis_resource.engine() as engine:
                    pdf.to_sql(table_name, engine, if_exists="append", index=False, method="multi")
            t_write = time.monotonic()
        except Exception as exc:
            t_write = time.monotonic()
            context.log.error("PostGIS write failed after %.1fs: %s", t_write - t_pandas, exc)
            raise

        t_total = t_write - t_start
        context.log.info("PostGIS write complete: %.1fs total", t_total)

        target_row_count = _count_postgis_rows(table_name, postgis_resource)
        _record_materialization(
            asset_key=f"{source_layer}/{source_table}",
            source_tier=source_layer,
            target_table=table_name,
            source_row_count=row_count,
            target_row_count=target_row_count,
            duration_seconds=round(t_total, 2),
            dagster_run_id=context.run_id,
        )

        return MaterializeResult(
            metadata={
                "source_path": source_path,
                "target_table": table_name,
                "row_count": row_count,
                "target_row_count": target_row_count,
                "is_parity": row_count == target_row_count,
                "write_method": write_method,
                "copy_threshold": copy_threshold,
                "timing_spark_read_s": round(t_spark - t_start, 2),
                "timing_to_pandas_s": round(t_pandas - t_spark, 2),
                "timing_postgis_write_s": round(t_write - t_pandas, 2),
                "timing_total_s": round(t_total, 2),
            }
        )

    return _postgis_asset


def _resolve_django_model(app_label: str, model_name: str):
    """Resolve a Django model class via the app registry.

    Imported lazily to keep import-time light when only Spark assets
    are used without the Django ORM.
    """
    import django

    if not django.apps.apps.ready:
        django.setup()
    return django.apps.apps.get_model(app_label, model_name)


def _count_postgis_rows(table_name: str, postgis_resource) -> int:
    from sqlalchemy import text

    with postgis_resource.engine() as engine:
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT count(*) FROM "{table_name}"'))
            return result.scalar()


def _record_materialization(
    *,
    asset_key: str,
    source_tier: str,
    target_table: str,
    source_row_count: int,
    target_row_count: int,
    duration_seconds: float,
    dagster_run_id: str,
) -> None:
    try:
        import django

        if not django.apps.apps.ready:
            django.setup()
        from socialwarehouse.warehouse.models.monitoring import MaterializationRecord

        MaterializationRecord.objects.create(
            asset_key=asset_key,
            source_tier=source_tier,
            target_table=target_table,
            source_row_count=source_row_count,
            target_row_count=target_row_count,
            is_parity=(source_row_count == target_row_count),
            duration_seconds=duration_seconds,
            dagster_run_id=dagster_run_id,
        )
    except Exception:
        pass
