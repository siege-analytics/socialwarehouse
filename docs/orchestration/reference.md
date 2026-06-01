# Orchestration — reference

Lookup tables for the orchestration layer's public API surface.

## Environment variables

Read by `socialwarehouse.orchestration.resources` at resource
initialization. Defaults are sane for local dev with file:// storage;
production sets them via `.env` or the deployment env config.

| Variable | Default | Read by | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | (none, required) | `PostGISResource.engine()` | Django settings module — `PostGISResource` calls `django.setup()` then reads `settings.DATABASES['default']` |
| `SW_WAREHOUSE_ROOT` | `s3a://socialwarehouse` | `WarehouseConfig.warehouse_root` + `delta.config` | Root path for Delta tables (e.g. `s3a://your-bucket`, `file:///tmp/sw-warehouse`) |
| `SW_CATALOG` | `socialwarehouse` | `WarehouseConfig.catalog` | Logical catalog namespace (instance projects override) |
| `SW_VINTAGE` | `2020` | `WarehouseConfig.vintage` | Default Census vintage / data-year for runs (overridable per run via run config) |
| `S3_ENDPOINT` | `http://10.10.0.10:9000` | `delta.config` | S3-compatible endpoint URL (used by Spark, not Dagster directly) |
| `S3_ACCESS_KEY` | (empty) | `delta.config` | S3 access key; required if `SW_WAREHOUSE_ROOT` starts with `s3a://` |
| `S3_SECRET_KEY` | (empty) | `delta.config` | S3 secret key; required if `SW_WAREHOUSE_ROOT` starts with `s3a://` |
| `DAGSTER_HOME` | (none, recommended) | Dagster runtime | Dagster's own state directory (run storage, schedule state). Production: separate Postgres via `dagster.yaml`. |
| `DAGSTER_PG_PASSWORD` | (none) | `dagster.yaml` (production) | Password for Dagster's own Postgres in production deployments |

`SW_*` env vars are the same ones `socialwarehouse/delta/config.py`
reads — Dagster and the Django/CLI paths see the same warehouse by
design.

## Resource classes

### `WarehouseConfig`

Carries instance-level warehouse configuration. Instance projects
override by constructing a different value and passing to
`Definitions(resources={"warehouse": WarehouseConfig(...)})`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `warehouse_root` | `str` | `SW_WAREHOUSE_ROOT` env or `s3a://socialwarehouse` | Delta table root path |
| `catalog` | `str` | `SW_CATALOG` env or `socialwarehouse` | Logical catalog namespace |
| `vintage` | `int` | `SW_VINTAGE` env or `2020` | Default vintage for asset runs |
| `partition_state` | `Optional[str]` | `None` | Optional state code to partition runs by (e.g. `"TX"`); `None` = full-warehouse |

### `SparkResource`

Wraps `socialwarehouse.delta.config.get_spark_session()`. Does NOT
reinvent the Spark session.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `app_name` | `str` | `"socialwarehouse-orchestration"` | Spark application name (only first call's value takes effect per JVM session) |
| `enable_sedona` | `bool` | `True` | Register Apache Sedona spatial extensions (default True because most SW assets are spatial) |

Usage in an asset compute function:

```python
def _my_compute(context, spark):
    # spark is already injected; no need to call get_spark_session()
    df = spark.read.format("delta").load(...)
```

If you need the resource directly (rare — the factory injects it for
you):

```python
def _my_compute(context):
    spark_resource: SparkResource = context.resources.spark
    with spark_resource.session(context) as spark:
        ...
```

### `PostGISResource`

Wraps a SQLAlchemy engine bound to Django's default DB connection.
Reads connection params from `django.conf.settings.DATABASES['default']`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `application_name` | `str` | `"socialwarehouse-orchestration"` | Postgres `application_name` for connection identification |
| `statement_timeout_ms` | `int` | `300_000` (5min) | Postgres `statement_timeout` in milliseconds; override per-asset for long materializations |

Methods:

- `engine()` — context manager yielding a SQLAlchemy engine (for `to_sql` and general queries)
- `raw_connection()` — context manager yielding a raw psycopg2 connection (for `COPY` operations)

Usage:

```python
def _my_compute(context):
    postgis: PostGISResource = context.resources.postgis
    with postgis.engine() as engine:
        df.to_sql("table", engine, if_exists="append", index=False)

    # For COPY operations (used by postgis_materialization_asset above the copy_threshold):
    with postgis.raw_connection() as conn:
        with conn.cursor() as cur:
            cur.copy_expert("COPY table FROM STDIN WITH CSV HEADER", buffer)
        conn.commit()
```

## Asset key conventions

The orchestration layer uses a 3-part asset key convention:

| Pattern | Example | Used for |
|---|---|---|
| `["warehouse", <layer>, <table>]` | `warehouse/bronze/addresses_raw` | Delta tables (bronze/silver/gold) |
| `["postgis", <app>, <model_lower>]` | `postgis/geo/address` | PostGIS materializations (target = Django model) |

The keys are produced by the factories:

- `delta_table_asset(layer=L, table=T)` → `AssetKey(["warehouse", L, T])`
- `postgis_materialization_asset(target_django_app_label=A, target_django_model_name=M)` → `AssetKey(["postgis", A, M.lower()])`

The `warehouse/<layer>/<table>` key intentionally mirrors the on-disk
Delta path produced by `delta.config.get_table_path(layer, table)` —
the asset graph and the on-disk layout stay coupled by construction.
If you grep for an asset key, the matching path is mechanical.

Asset selection in `dagster asset materialize` uses the same syntax:

```bash
dagster asset materialize --select 'warehouse/silver/*'    # all silver Delta assets
dagster asset materialize --select 'postgis/geo/*'         # all geo PostGIS assets
dagster asset materialize --select 'warehouse/bronze/addresses_raw+'  # bronze + all downstream
```

## Factory API

### `delta_table_asset(...) -> AssetsDefinition`

```python
def delta_table_asset(
    *,
    layer: str,              # 'bronze' | 'silver' | 'gold'
    table: str,              # table name (matches delta/tables.py)
    deps: Iterable[str] = None,    # list of 'layer/table' strings
    compute_fn: Callable[[AssetExecutionContext, SparkSession], None],
    description: Optional[str] = None,
    group_name: Optional[str] = None,  # defaults to layer
) -> AssetsDefinition: ...
```

- `compute_fn(context, spark)` writes the Delta table at
  `get_table_path(layer, table)`.
- Returns an `AssetsDefinition` with key
  `["warehouse", layer, table]`, deps wired, `SparkResource` injected.
- Materialization metadata: `{"path": <delta-path>, "row_count": int, "layer": str}`.

### `postgis_materialization_asset(...) -> AssetsDefinition`

```python
def postgis_materialization_asset(
    *,
    source_layer: str,             # 'silver' | 'gold'
    source_table: str,             # source Delta table name
    target_django_app_label: str,  # e.g. 'geo'
    target_django_model_name: str, # e.g. 'Address'
    compute_sql: Callable[[SparkSession, str], DataFrame],
    copy_threshold: int = 100_000, # rows above which COPY is used instead of to_sql
    description: Optional[str] = None,
    group_name: str = "postgis",
) -> AssetsDefinition: ...
```

- `compute_sql(spark, source_path)` returns a DataFrame shaped for
  the target Django model.
- Returns an `AssetsDefinition` with key
  `["postgis", app_label, model_name.lower()]`, dep on
  `["warehouse", source_layer, source_table]`, both `SparkResource`
  and `PostGISResource` injected.
- **Write method**: when `row_count > copy_threshold`, uses PostgreSQL
  `COPY FROM STDIN WITH CSV HEADER` via psycopg2 (faster for large
  datasets). Below the threshold, uses `pandas.to_sql()`.
- **Observability metadata** in `MaterializeResult`:

  | Key | Type | Description |
  |---|---|---|
  | `source_path` | `str` | Delta table path |
  | `target_table` | `str` | PostGIS table name |
  | `row_count` | `int` | Number of rows written |
  | `write_method` | `str` | `"copy"` or `"to_sql"` |
  | `copy_threshold` | `int` | Configured threshold |
  | `timing_spark_read_s` | `float` | Seconds for Spark read + compute_sql |
  | `timing_to_pandas_s` | `float` | Seconds for toPandas conversion |
  | `timing_postgis_write_s` | `float` | Seconds for PostGIS write |
  | `timing_total_s` | `float` | Total wall-clock seconds |

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `ImportError: No module named 'dagster'` when importing SW | Tried to import `socialwarehouse.orchestration` without `[orchestration]` extra installed | Install with `pip install -e ".[orchestration]"` |
| `RuntimeError: WAREHOUSE_ROOT=... requires S3 credentials` | `SW_WAREHOUSE_ROOT` is s3a:// but `S3_ACCESS_KEY`/`S3_SECRET_KEY` are empty | Set the env vars OR point `SW_WAREHOUSE_ROOT` at a `file://` path for dev |
| `django.core.exceptions.ImproperlyConfigured: DJANGO_SETTINGS_MODULE` | `PostGISResource` initialized without Django settings | Set `DJANGO_SETTINGS_MODULE=socialwarehouse.settings.dev` in `.env` |
| `dagster._core.errors.DagsterInvariantViolationError: AssetKey ['warehouse', ...] is not part of the set of assets` | Dep asset declared with wrong key | Verify the dep's `layer/table` matches the upstream asset's actual key (use `warehouse/<layer>/<table>` form) |
| `py4j.protocol.Py4JJavaError: ... Delta` | Delta extension not registered | Ensure `SparkResource` is used (which calls `delta.config.get_spark_session()` — that's where the Delta extensions are registered) |
| `py4j.protocol.Py4JJavaError: ... Sedona` | Sedona not registered, but asset uses spatial operations | Set `SparkResource(enable_sedona=True)` (default) and confirm `apache-sedona` is installed (`pip install -e ".[spark]"`) |
| Asset graph in UI is empty / "no assets" | Definitions module not discovered | Verify launch command: `dagster dev -m socialwarehouse.orchestration` (not `python -m`); confirm `socialwarehouse.orchestration.defs` exists |
| Sensor enabled but never fires | Daemon not running OR sensor probe failing | `dagster dev` output should show "daemon running"; check Sensors tab → Cursor → recent evaluations for errors |
| `to_sql` extremely slow / OOM | Materialization above ~500K rows hits the `toPandas` bottleneck | Set `copy_threshold` (default 100K) — loads above the threshold automatically use PostgreSQL COPY (SW#280) |

## Pinned Dagster version

```toml
[project.optional-dependencies]
orchestration = [
    "dagster>=1.9,<2",
    "dagster-webserver>=1.9,<2",
    "dagster-postgres>=0.25,<1",
    "dagster-spark>=0.25,<1",
]
```

The `1.9,<2` pin locks the major version. Bumping the upper bound
requires verifying the API surface this layer uses
(`ConfigurableResource`, `@asset`, `AssetKey`, `MaterializeResult`,
`Definitions`, `define_asset_job`, `ScheduleDefinition`,
`AssetSelection.groups`, `@sensor`, `SensorResult`, `RunRequest`,
`SkipReason`, `SourceAsset`) is still stable.

## See also

- [README.md](README.md) — index + Mermaid asset graph
- [how-to-add-asset-to-existing-domain.md](how-to-add-asset-to-existing-domain.md) — author workflow
- [how-to-operate.md](how-to-operate.md) — run/debug/deploy
- [instance-project-guide.md](instance-project-guide.md) — for instance projects forking SW
