# Instance project guide: extending the SW Dagster orchestration

This guide is for **instance projects** that fork the socialwarehouse
template for a specific geography or domain combination (e.g.
UK-warehouse, EU-warehouse, regional-economic-warehouse) and need to
inherit improvements made to the SW orchestration layer without
re-implementing them.

## Mental model

- **socialwarehouse (SW)** provides the *template*: resources, asset
  factories, schedules + sensors examples, the canonical
  bronze/silver/gold layout in `delta/`, and the Dagster `Definitions`
  object at `socialwarehouse.orchestration.definitions.defs`.
- **Your instance project** consumes SW as a dependency, adds its own
  domain assets, and rebuilds its own `Definitions` object — composing
  SW's pieces with its own without monkey-patching base.

The orchestration layer is designed so that adding a new domain or
overriding warehouse config is mechanical: copy the
`socialwarehouse.orchestration.assets.geo` pattern, register, done.

## Adding a new domain to your warehouse

Say your instance project needs an `electoral` domain that doesn't
exist in upstream SW (or needs to override SW's `geo` with a
country-specific schema).

### 1. Define your Delta schemas

In your instance project, add `<your_project>/delta/tables.py`
mirroring SW's pattern:

```python
from socialwarehouse.delta.config import get_table_path
from pyspark.sql.types import StructType, StructField, StringType  # etc.

ELECTORAL_BRONZE_VOTERS_SCHEMA = StructType([
    StructField("voter_id", StringType(), nullable=False),
    # ... more fields ...
])

def electoral_bronze_voters_path():
    return get_table_path("bronze", "electoral_voters")
```

### 2. Write a domain asset module

In your instance project, add
`<your_project>/orchestration/assets/electoral.py`:

```python
from dagster import AssetKey, SourceAsset
from socialwarehouse.orchestration.asset_factories import (
    delta_table_asset,
    postgis_materialization_asset,
)

# Bronze (declared, ingested upstream of Dagster):
voters_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "electoral_voters"]),
    description="Raw voter registration rows from county ingest.",
    group_name="bronze",
)


def _compute_voters_typed(context, spark):
    from socialwarehouse.delta.config import get_table_path
    bronze = spark.read.format("delta").load(get_table_path("bronze", "electoral_voters"))
    typed = bronze.selectExpr(
        "CAST(voter_id AS STRING) AS voter_id",
        # ... typing transform ...
    )
    typed.write.format("delta").mode("overwrite").save(
        get_table_path("silver", "electoral_voters_typed")
    )


voters_typed = delta_table_asset(
    layer="silver",
    table="electoral_voters_typed",
    deps=["bronze/electoral_voters"],
    compute_fn=_compute_voters_typed,
    description="Typed voter records (silver).",
)


all_assets = [voters_raw, voters_typed]
```

### 3. Rebuild Definitions

In your instance project, add
`<your_project>/orchestration/definitions.py`:

```python
from dagster import Definitions
from socialwarehouse.orchestration.resources import (
    SparkResource, PostGISResource, WarehouseConfig,
)
from socialwarehouse.orchestration.assets import geo as sw_geo
from socialwarehouse.orchestration.schedules import all_schedules as sw_schedules
from socialwarehouse.orchestration.schedules import all_jobs as sw_jobs
from socialwarehouse.orchestration.sensors import all_sensors as sw_sensors

from your_project.orchestration.assets import electoral

defs = Definitions(
    assets=sw_geo.all_assets + electoral.all_assets,
    jobs=sw_jobs,  # + your own
    schedules=sw_schedules,  # + your own
    sensors=sw_sensors,  # + your own
    resources={
        "warehouse": WarehouseConfig(catalog="your-warehouse-catalog"),
        "spark": SparkResource(app_name="your-project-orchestration"),
        "postgis": PostGISResource(application_name="your-project-orchestration"),
    },
)
```

Then run `dagster dev -m your_project.orchestration`.

## Overriding warehouse config without code changes

The `WarehouseConfig`, `SparkResource`, and `PostGISResource` all
read their defaults from env vars (`SW_WAREHOUSE_ROOT`,
`SW_CATALOG`, `SW_VINTAGE`, `DJANGO_SETTINGS_MODULE`). Instance
projects can override entirely via `.env` without touching code:

```
SW_WAREHOUSE_ROOT=s3a://uk-warehouse
SW_CATALOG=uk_warehouse
SW_VINTAGE=2021
DJANGO_SETTINGS_MODULE=your_project.settings.prod
```

## Overriding a specific SW asset

If you need to override SW's `addresses_typed` silver asset (different
typing pass, instance-specific transforms), declare your own asset
with the same key — Dagster's last-registration-wins behavior means
your asset replaces the SW one in your project's Definitions:

```python
from dagster import AssetKey
from socialwarehouse.orchestration.asset_factories import delta_table_asset

def _my_typing(context, spark):
    # ... your custom typing transform ...
    pass

addresses_typed_override = delta_table_asset(
    layer="silver",
    table="addresses_typed",  # SAME key as SW's asset
    deps=["bronze/addresses_raw"],
    compute_fn=_my_typing,
)
```

Only include `addresses_typed_override` (not SW's original) in your
project's `Definitions.assets`. Downstream gold + PostGIS assets
continue to work because they depend on the asset key, not the
specific definition.

## Adopting SW orchestration improvements

When SW ships an improvement to the orchestration layer (new factory,
new resource field, better sensor pattern), your instance project
picks it up by bumping the `socialwarehouse` pin in your
`pyproject.toml`. No code change required for improvements that don't
change the public API of `socialwarehouse.orchestration.*`.

If SW changes a public API in a non-backwards-compatible way, the SW
release notes will name the migration step. The factories
(`delta_table_asset`, `postgis_materialization_asset`) and the
resource classes (`SparkResource`, `PostGISResource`,
`WarehouseConfig`) are the stable public surface; treat the asset
modules under `socialwarehouse.orchestration.assets.*` as examples to
copy-extend, not as a stable import surface.

## What NOT to do

- **Do NOT vendor the SW orchestration package into your instance
  project.** That breaks the upgrade path. Depend on SW as a regular
  install.
- **Do NOT modify `socialwarehouse/orchestration/*` files in your
  instance project.** Override via your own `Definitions` instead.
- **Do NOT use Celery to schedule Dagster jobs or vice versa.** They
  serve different concerns (web-app async vs warehouse pipeline) and
  composing them adds operational complexity without clarity.
- **Do NOT mix Dagster's run-storage Postgres with SW's domain
  Postgres unless your scale is small.** For production, run a
  separate Postgres instance for Dagster (see Dagster's deployment
  docs). For local dev, sharing the SW Postgres is fine.

## Pre-author inventory expectation

Per `[rule:authoring-against-state]` rule 6, any change to an asset's
compute function should be preceded by a pre-author inventory in the
ticket: data-shape measurement of the source table, config-state
inventory of the Spark/Postgres environment, and a falsifiable
hypothesis of what the asset will compute. The factories don't
enforce this; the discipline is on the author of each domain module.
The orchestration layer's job is to make the discipline mechanical
once exercised — the asset keys + factory wiring give the reviewer a
clean spec to check the implementation against.
