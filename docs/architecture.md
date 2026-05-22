# Architecture

Project-level architectural principles for SocialWarehouse. These constrain the design of every feature and sub-issue. Per-initiative design notes live in [`docs/designs/`](designs/); this document is the level above — the rules those design notes must respect.

## Warehouse first, web app last

**The web application is always last. It is a distribution mechanism for what is in the warehouse.**

The warehouse is the system. The web application is one of several thin serving layers on top of it (the others are the DRF API, the CLI, the Spark notebooks, and direct SQL access). Designing web-app-first commits the data model to whatever Django ORM ergonomics suggest, instead of what the analytical substrate requires.

### Design order is fixed

Every feature that touches data follows this order:

1. **Delta Lake schemas** (`socialwarehouse/delta/`) — the canonical, bulk-loadable, partition-prunable substrate. Bronze / Silver / Gold medallion. Schemas declared as PySpark `StructType`.
2. **PostGIS star-schema dimensional models** (`socialwarehouse/warehouse/`) — the transactional/serving tier, materialized from silver Delta tables. Dims and Facts, FK-joined, indexed for hot-path queries.
3. **Django ORM** — the read API for the web app, admin, and DRF surfaces. Reads via the standard star-schema path.

Inverting this order is wrong-end-up. A design that begins with `class Foo(models.Model)` is web-app-coupled and needs reordering before implementation.

### Sub-issue ordering reflects this

When an initiative contains both warehouse work and web-app surfaces, the warehouse sub-issues land first and ship before any web-app sub-issue starts. Web-app sub-issues are explicitly downstream-of and read-only-on warehouse output.

### Sanity check

Before presenting any design, ask: **would this work if no web app existed?** If the answer is no, the design is web-app-coupled. Reorder.

## Two warehouse tiers

Both tiers are canonical; both are intentionally present.

### Tier 1 — Delta Lake medallion

Located in `socialwarehouse/delta/`. Three layers:

- **Bronze** — raw ingested data, vendor-native column names, mostly `StringType`, minimal validation. Partitioned by natural cuts (state, vendor).
- **Silver** — typed, validated, geocoded, vendor-neutral canonical shapes. The analytical entry point. Joins across silver tables are clean.
- **Gold** — enriched, denormalized for specific analytical workloads. Built lazily as workloads demand them.

Schemas live in `socialwarehouse/delta/tables.py` as PySpark `StructType` declarations, registered in the `TABLES = {...}` dict. The `create_table(spark, name)` helper materializes them.

### Tier 2 — PostGIS star schema

Located in `socialwarehouse/warehouse/`. Django-managed models in PostGIS, organized as a star schema:

- **Dimensions** (`warehouse/models/dimensions.py`) — `DimGeography`, `DimTime`, `DimSurvey`, `DimCensusVariable`, `DimRedistrictingCycle`, etc. Most are managed by Django; `DimGeography` is SCD2 because geographies are revised within a vintage.
- **Facts** (`warehouse/models/facts.py`) — `FactACSEstimate`, `FactDecennialCount`, `FactUrbanicity`, `FactElectionResult`, etc. FK to dimensions; indexed for hot-path queries.

Loaded from silver Delta tables via Spark→PostGIS materialization jobs (or, for smaller datasets, direct ORM ingest).

### Relationship between the tiers

Delta is the canonical-most analytical substrate; PostGIS is the serving tier optimized for sub-second queries from the web app and admin. The two are intentionally redundant: Delta handles bulk analytics; PostGIS handles transactional reads and joins to `geo.Address`. Eventual consistency between them is acceptable; the materialization job is idempotent.

## Where the web app fits

The web app (Django views + DRF API + admin) is a downstream read-only consumer of the PostGIS star schema. It does not own data; it surfaces what the warehouse produces.

This means:

- Web-app views map cleanly to star-schema queries. If a view needs a query the star schema can't answer, the right response is usually a new gold-tier Delta table + materialization, not a view-specific table.
- The web app is replaceable. The warehouse is not. A future Phoenix / Next.js / etc. UI would consume the same star schema; the data model doesn't move.
- Web-app schema changes are downstream of warehouse schema changes, never the reverse.

## Cross-references

- Initiative SW#250 (US Civic/Electoral template) — first initiative to be explicitly constrained by this principle.
- Sub-issue SW#251 design note (`sessions/260502-vital-channel/plans/think-sw251-person-model.md` in the workspace) — the canonical example of a warehouse-first design (v2 supersedes a v1 that was web-app-first).
- Per-initiative design notes: [`docs/designs/`](designs/).
- Contributor discipline: [`CONTRIBUTING.md`](../CONTRIBUTING.md).
