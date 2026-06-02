# Use SocialWarehouse as a template

SocialWarehouse is **a template, not a finished product**. The US-default configuration ships with geography, civic, demographic, and economic domains keyed to US Census boundaries — but the architecture (Delta Lake medallion → PostGIS star-schema → Django ORM, with Dagster orchestration on top) works for any boundary-keyed multi-domain warehouse. Instance projects fork SW, rename the package, swap or add geographies/domains, and inherit the patterns from upstream.

## What "template" actually means here

SW's template-readiness is tracked under [SW#189](https://github.com/siege-analytics/socialwarehouse/issues/189) and broken into six design tracks ([B/C/D/E/F/G under `docs/designs/template-*.md`](../designs/)):

| Track | Concern | Status |
|---|---|---|
| **B** — Vintage polymorphization | Make all data vintage-aware so historical decades can coexist | Design landed |
| **C** — Boundary catalog | The set of boundary types the warehouse keys on (state/county/tract/zcta/place/cbsa/school_district/...) | Implementation complete |
| **D** — Demographic ingest | Pluggable pattern for demographic data sources (ACS, decennial, etc.) | Design landed |
| **E** — Economic ingest | Pluggable pattern for economic data sources (QCEW, BEA, IRS SOI, etc.) | Design landed |
| **F** — Civic ingest | Pluggable pattern for civic data sources (NCES, special districts, etc.) | Design landed |
| **G** — Quickstart + template-init | Automated fork+rename+seed flow | Design landed; implementation pending |

The patterns from B-F are what an instance project consumes. The G mechanism (automated init) is coming; until then, the fork+rename flow is manual (see [how-to-fork-and-rename.md](how-to-fork-and-rename.md)).

## Who should fork SocialWarehouse

You should consider forking SW if you're building:

- A **boundary-keyed multi-domain warehouse** for a geography that isn't the US (UK with Ordnance Survey + ONS Census; EU with Eurostat NUTS; Canada with Statistics Canada; etc.)
- A **topic-specific warehouse** that combines several public datasets with consistent geographic keying (e.g. a public-health warehouse combining CDC + Census + EPA at the county level)
- A **regional warehouse** for a sub-national geography (state-level, MSA-level, watershed-level)
- An **augmented US warehouse** that needs domains SW doesn't ship (e.g. environmental, transit, real-estate)

You probably **don't need to fork** SW if you're:

- Adding a new data source within an existing SW domain (just contribute upstream)
- Using SW as-is for US analysis (just install + use)
- Running a one-off analysis that doesn't need warehouse persistence (use the Delta layer directly, no template needed)

## What you inherit; what you write

| Layer | Inherited from SW | You write |
|---|---|---|
| **Delta Lake medallion** (`delta/`) | `get_spark_session`, `get_table_path`, table-path conventions, enrichment helpers | Your domain's bronze schemas + the silver/gold transforms |
| **PostGIS star schema** (`warehouse/`) | `DimGeography` SCD2, `DimTime`, `DimSurvey`, fact-table patterns | Your domain's specific dim/fact tables; instance-specific FK extensions |
| **Boundary catalog** (`geo/models/`) | `Address`, `AddressBoundaryPeriod`, `_BOUNDARY_TYPES` registry, F11 helpers | Your geography's boundary types (see [how-to-swap-geography.md](how-to-swap-geography.md)) |
| **Django REST API** (`api/`) | `geocode`, `reverse_geocode`, `boundaries`, `proximity`, `intersections`, `civic_lookup` patterns | Your domain-specific endpoints |
| **Dagster orchestration** (`orchestration/`) | `WarehouseConfig`, `SparkResource`, `PostGISResource`, `delta_table_asset`, `postgis_materialization_asset` factories, demo geo asset graph | Your domain asset modules (`orchestration/assets/<domain>.py`); your schedules + sensors |
| **Django web app frame** | Grappelli admin + DRF browsable API under `/webapp/` prefix | Your instance-specific views, admin extensions |
| **Project structure** | Package layout, settings hierarchy (`base`/`dev`/`prod`/`test`), Makefile + docker-compose pattern | Your renamed package + Django apps + .env |

## How-to docs in this directory

| Doc | When to read |
|---|---|
| [README.md](README.md) (this file) | Landing here for the first time, want the overview + decision orientation |
| [how-to-fork-and-rename.md](how-to-fork-and-rename.md) | You've decided to fork — concrete steps to clone, rename, init |
| [how-to-swap-geography.md](how-to-swap-geography.md) | Your instance project uses non-US boundaries (UK Ordnance Survey, EU NUTS, Canada Statistics Canada, etc.) |
| [how-to-add-a-new-domain.md](how-to-add-a-new-domain.md) | You're adding a domain SW doesn't ship (environmental, transit, real-estate, public-health, etc.) |
| [how-to-upgrade-from-upstream.md](how-to-upgrade-from-upstream.md) | You've forked, time has passed, and you want to absorb SW improvements without churning your fork |

## Other doc surfaces you'll need

- [`docs/architecture.md`](../architecture.md) — warehouse-first principle, the design-order rule (Delta → PostGIS → Django, never the reverse), tier relationships
- [`docs/quickstart.md`](../quickstart.md) — `git clone` to seeded dev instance in under 1 hour (US-default), useful as a sanity check before forking
- [`docs/designs/template-*.md`](../designs/) — the design decisions per track (read the relevant one before forking that part of the template)
- [`docs/orchestration/`](../orchestration/README.md) — Dagster orchestration layer (how-to-add-asset, how-to-operate, reference, plus the instance-project guide specifically for Dagster extension)
- [`docs/entities/`](../entities/) — per-entity reference for the canonical models (boundary catalog, Address cache, fact tables)

## Pre-author inventory discipline (applies to forks too)

Per [`[rule:authoring-against-state]`](https://github.com/siege-analytics/claude-configs-public/blob/main/skills/_authoring-against-state-rules.md) rule 6, every fork-step (especially geography swap and new-domain addition) should be preceded by a pre-author inventory in the relevant ticket. The discipline is the same as for asset additions: read the inputs, enumerate the open questions, measure the contact points, record findings before authoring. The how-to docs in this directory embed inventory templates as Step 0.

## When NOT to use this template

- **Single-table analytical projects.** Use `pandas` or `polars` directly; SW's warehouse layers are overhead.
- **Real-time / streaming workloads.** SW is batch-oriented (Delta refreshes, Dagster schedules). Streaming-first systems should look at Kafka + Flink / Spark Streaming patterns, not this template.
- **Pure web apps with no warehouse.** A standalone GeoDjango project is a better fit; SW is a warehouse stack with a web layer on top.
- **Project that needs a different orchestration framework.** If you've committed to Airflow / Prefect / dbt-only, the SW Dagster layer is wrong shape — though the Delta + PostGIS pieces are usable independently.

## See also

- [SW#189](https://github.com/siege-analytics/socialwarehouse/issues/189) — template-readiness parent initiative
- [SW#275](https://github.com/siege-analytics/socialwarehouse/issues/275) — Dagster orchestration scaffold (template-track follow-on)
- Architecture: [`docs/architecture.md`](../architecture.md)
- Contribution guide: [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)
