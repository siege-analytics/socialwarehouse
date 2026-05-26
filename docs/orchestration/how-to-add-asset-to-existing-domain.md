# How to add a new asset to an existing domain

This is the workflow for adding a single asset (e.g. a new silver
transformation or a new gold materialization) to a domain that
**already exists** in SW. If you're adding a brand-new domain or
forking SW into an instance project, read
[instance-project-guide.md](instance-project-guide.md) instead.

## TL;DR

1. Define the Delta schema in `socialwarehouse/delta/tables.py` (if it's a new table).
2. Write a compute function that takes `(context, spark)` and writes the table.
3. Call `delta_table_asset(...)` to wrap it; export from the domain module.
4. Add it to the domain module's `all_assets` list.
5. Post a pre-author inventory to the relevant ticket (per rule 6).
6. Test in `dagster dev`; commit + PR.

## Step-by-step

### 0. Pre-author inventory (rule 6) — do this FIRST

Before writing the asset, post a pre-author inventory to the GitHub
issue tracking this work. The inventory makes the assumptions
explicit and gives the reviewer a clean spec to check the diff
against. Template:

```markdown
## Pre-author inventory for `<asset key>`

### Inputs read
- Ticket: <link>
- Upstream Delta table(s) the asset will read: <paths>
- Downstream consumers (other assets, Django models, PostGIS tables): <list>

### Knowledge requirements
- What is the row count of each upstream Delta table? (measure live, don't guess)
- What is the schema drift between upstream and target? Any new columns?
- What is the dedup key / merge strategy?
- Does this asset depend on a partition column (state, vintage, date)?
- Are there downstream consumers that pin the asset's output schema?

### Contact-point measurements (per `[rule:authoring-against-state]`)
- **data-shape (rule 1):** row counts on the upstream tables
- **config-state (rule 2):** Spark Connect config snapshot if cluster-resource demands change
- **plan-shape (rule 4):** if the asset chains many unions, count the depth
- **version-resolution (rule 5):** N/A unless adding new public symbols

### Surface areas beyond rules 1-5
- Existing similar assets in the domain (don't duplicate)
- Existing management commands that may compose with or be obsoleted by this asset

### Hypothesis
"The asset `warehouse/<layer>/<table>` will read `{upstream_table}` and
produce a Delta table at `{target_path}` containing `{row_count}` rows
with schema `{schema}`. The merge strategy is `{strategy}`. Downstream
consumer `{consumer}` will see the new asset key."
```

### 1. Define the Delta schema (if new table)

In `socialwarehouse/delta/tables.py`, add the schema following the
existing bronze / silver / gold conventions:

```python
from pyspark.sql.types import StructType, StructField, StringType, IntegerType
from .config import get_table_path

GEO_SILVER_ADDRESSES_GEOCODED_SCHEMA = StructType([
    StructField("address_id", StringType(), nullable=False),
    StructField("lat", DoubleType(), nullable=True),
    StructField("lon", DoubleType(), nullable=True),
    StructField("geocode_quality", IntegerType(), nullable=True),
    # ... more fields ...
])

def addresses_geocoded_path():
    return get_table_path("silver", "addresses_geocoded")
```

Skip this step if the table already exists in `delta/tables.py` (the
asset just materializes an existing schema).

### 2. Write the compute function

The compute function receives `(context, spark)` and is responsible
for writing the Delta table at the target path. It should NOT
reimplement Spark session creation or path computation — both come
from existing socialwarehouse infrastructure.

```python
# in socialwarehouse/orchestration/assets/geo.py

def _compute_addresses_geocoded(context, spark):
    """Geocode silver.addresses_typed -> silver.addresses_geocoded."""
    from socialwarehouse.delta.config import get_table_path

    source_path = get_table_path("silver", "addresses_typed")
    target_path = get_table_path("silver", "addresses_geocoded")

    typed = spark.read.format("delta").load(source_path)
    context.log.info("typed row count: %d", typed.count())

    # Geocoding transform — invoke existing helper or write inline.
    # For non-trivial transforms, factor into delta/enrichment.py
    # rather than inline-in-asset (so the same transform can be
    # called from non-Dagster paths too).
    geocoded = typed.withColumn("lat", _lookup_lat(typed["address"])) \
                    .withColumn("lon", _lookup_lon(typed["address"])) \
                    .withColumn("geocode_quality", _quality_score(typed["address"]))

    geocoded.write.format("delta").mode("overwrite").save(target_path)
```

Conventions:
- Use `context.log.info(...)` for asset-progress messages — they
  surface in the Dagster UI's run log.
- Measure-before-write: log the row count of the source before the
  transform runs (cheap; load-bearing for catching upstream drift).
- The mode (`overwrite` vs `append` vs `merge`) is a deliberate
  choice — `overwrite` is the default for vintage-rebuilds; `append`
  for incremental loads; `merge` for upserts.

### 3. Wrap with the factory

In the same domain module:

```python
addresses_geocoded = delta_table_asset(
    layer="silver",
    table="addresses_geocoded",
    deps=["silver/addresses_typed"],
    compute_fn=_compute_addresses_geocoded,
    description="Geocoded addresses (silver). Lat/lon assigned via the lookup service.",
)
```

The factory:
- Derives the asset key as `["warehouse", "silver", "addresses_geocoded"]`
- Wires the dep as `AssetKey(["warehouse", "silver", "addresses_typed"])`
- Injects the `SparkResource` so `compute_fn` gets a live `spark` session
- Reports the materialization result with row count + path metadata

### 4. Register in `all_assets`

At the bottom of the domain module:

```python
all_assets = [
    addresses_raw,
    addresses_typed,
    addresses_geocoded,   # ← new asset
    addresses_enriched,
    geo_address_postgis,
]
```

The `Definitions` object in `socialwarehouse/orchestration/definitions.py`
discovers assets from `geo.all_assets`; no separate registration needed.

### 5. Add the asset to a schedule or sensor (optional)

If the new asset should be on the nightly refresh, the existing
`geo_refresh_job` already selects `AssetSelection.groups("silver",
"gold", "postgis")` — any asset in those groups is auto-included.

If the new asset needs its own schedule (different cadence, different
selection), add it to `socialwarehouse/orchestration/schedules.py`:

```python
addresses_geocoded_hourly_job = define_asset_job(
    name="addresses_geocoded_hourly",
    selection=AssetSelection.assets(addresses_geocoded),
)

addresses_geocoded_hourly_schedule = ScheduleDefinition(
    job=addresses_geocoded_hourly_job,
    cron_schedule="0 * * * *",  # every hour
    execution_timezone="UTC",
)

all_schedules.append(addresses_geocoded_hourly_schedule)
all_jobs.append(addresses_geocoded_hourly_job)
```

### 6. Test locally

```bash
# Restart dagster dev (it auto-reloads on file changes but a fresh
# start avoids stale-import surprises)
dagster dev -m socialwarehouse.orchestration

# Confirm the new asset shows up in the UI graph
# (open http://localhost:3000, navigate to Assets)

# Materialize the new asset against a local warehouse
dagster asset materialize -m socialwarehouse.orchestration \
  --select 'warehouse/silver/addresses_geocoded'
```

If the materialization fails, check:
- The dep asset (`warehouse/silver/addresses_typed`) has been
  materialized first (or is materialized in the same run via
  `--select '*addresses_geocoded'`)
- The target Delta path is writable (`ls -la $SW_WAREHOUSE_ROOT/silver/`)
- The Spark session is created with Sedona enabled if the asset
  uses spatial operations

### 7. Write the asset test

In `tests/orchestration/test_<domain>_assets.py`:

```python
def test_addresses_geocoded_asset_keys():
    from socialwarehouse.orchestration.assets.geo import addresses_geocoded
    from dagster import AssetKey

    assert addresses_geocoded.key == AssetKey(["warehouse", "silver", "addresses_geocoded"])
    assert AssetKey(["warehouse", "silver", "addresses_typed"]) in addresses_geocoded.dependency_keys
```

This doesn't run the compute function (which needs a live Spark
cluster); it verifies the asset graph topology is correct, which
catches the most common "wrong key" / "missing dep" errors.

### 8. Commit + open PR

```bash
git checkout -b feat/<domain>-<asset>-asset
git add socialwarehouse/orchestration/assets/<domain>.py tests/orchestration/test_<domain>_assets.py
git commit -m "feat(orchestration): add <domain>/<asset> asset (#<ticket>)"
git push -u origin feat/<domain>-<asset>-asset
gh pr create --base develop ...
```

Per the workspace's `[rule:self-review]` discipline, include a
self-review artifact path in the commit's trailer block.

## Common variations

### Asset that materializes to PostGIS (not Delta)

Use `postgis_materialization_asset` instead of `delta_table_asset`:

```python
my_postgis_asset = postgis_materialization_asset(
    source_layer="gold",
    source_table="addresses_enriched",
    target_django_app_label="geo",
    target_django_model_name="Address",
    compute_sql=_shape_for_address_model,
)
```

The factory handles the Delta read + Pandas conversion + SQLAlchemy
write. For datasets above ~500K rows, see SW#280 for the planned
COPY-based path (currently uses `to_sql`).

### Asset that depends on multiple upstreams

```python
addresses_joined = delta_table_asset(
    layer="silver",
    table="addresses_joined",
    deps=["silver/addresses_typed", "silver/persons_typed"],
    compute_fn=_compute_addresses_joined,
)
```

Inside the compute function, both source paths come from
`get_table_path()` calls; Dagster's dep wiring guarantees both
upstreams are materialized before this asset runs.

### Asset that's a SourceAsset (declared, not produced)

For raw bronze data ingested by an upstream pipeline (not by
Dagster), declare a `SourceAsset` instead of using the factory:

```python
from dagster import AssetKey, SourceAsset

raw_voters = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "voters_raw"]),
    description="Raw voter rows from the upstream ingest pipeline.",
    group_name="bronze",
)
```

Use a sensor (see `sensors.py`) to detect when the raw asset has new
data and request downstream materialization.

## What NOT to do

- **Do NOT reimplement `get_spark_session` or `get_table_path`** in
  your asset. Use the canonical functions from `delta/config.py`.
- **Do NOT inline a large transform in the asset's compute function**
  if it could be called from non-Dagster paths. Factor into
  `delta/enrichment.py` (or a new `delta/<topic>.py` module) and
  invoke from the asset. This keeps the orchestration layer thin and
  the transforms reusable.
- **Do NOT use Celery to schedule an asset.** Use a Dagster schedule
  or sensor. The two systems serve different concerns.
- **Do NOT skip the pre-author inventory.** The discipline is the
  point — assets that drift from upstream schemas without an
  inventory record become the SW#2094-class incident the rule
  exists to prevent.

## See also

- [reference.md](reference.md) — full env var matrix, asset key conventions, factory API
- [how-to-operate.md](how-to-operate.md) — running, debugging, deploying
- [instance-project-guide.md](instance-project-guide.md) — for instance projects forking SW
- [SW#275](https://github.com/siege-analytics/socialwarehouse/issues/275) — parent ticket for the orchestration scaffold
- [`[rule:authoring-against-state]`](https://github.com/siege-analytics/claude-configs-public/blob/main/skills/_authoring-against-state-rules.md) — the discipline rule the pre-author inventory implements
