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

## App structure

### Domain apps (ontology)

| App | Purpose | Key models |
|---|---|---|
| `socialwarehouse.core` | Abstract mixins, UUID generation, polymorphic supertypes | `SourceAwareModel`, `IdentifiableModel`, `Agent`, `AgentSubtype` |
| `socialwarehouse.agents` | Entity-resolved actors | `Person`, `Committee`, `Organization`, `Classification`, `Role`, `Relationship*` (6 types) |
| `socialwarehouse.political` | Political structure | `Office`, `Seat`, `Election`, `ElectoralContest`, `OfficeTerm` |
| `socialwarehouse.transactions` | Financial flows | `Contribution`, `Expenditure`, `Transfer`, `Obligation`, `ObligationEvent`, `TransactionGroup` |
| `socialwarehouse.events` | Unified event supertype | `Event`, `EventParticipant`, `CorporateEvent`, `SpatioTemporalEvent`, `ElectoralEvent` |
| `socialwarehouse.geo` | Geography, boundaries, vintages | `Address`, `AddressBoundaryPeriod`, `PrecinctVTDIntersection`, `Vintage` (7 subtypes) |

### Infrastructure apps

| App | Purpose |
|---|---|
| `socialwarehouse.warehouse` | PostGIS star schema (dims + facts) |
| `socialwarehouse.delta` | Delta Lake table definitions and config |
| `socialwarehouse.demographic` | Census/ACS ingest pipelines |
| `socialwarehouse.economic` | BLS QCEW / BEA / IRS SOI ingest |
| `socialwarehouse.civic` | NCES school data ingest |

### API surface

| Prefix | App | Endpoints |
|---|---|---|
| `/api/geo/` | `socialwarehouse.api.geo` | civic_lookup, boundary queries |
| `/api/warehouse/` | `socialwarehouse.api.warehouse` | dimension/fact read API |
| `/api/agents/` | `socialwarehouse.api.agents` | person, committee, organization, classification, role |
| `/api/political/` | `socialwarehouse.api.political` | office, seat, election, contest, term |
| `/api/transactions/` | `socialwarehouse.api.transactions` | contribution, expenditure, transfer, obligation |
| `/api/events/` | `socialwarehouse.api.events` | event (with participants + subtype details) |

## Polymorphic canonical-truth layer (core supertypes)

SW canonical supports adopters whose source data carries multi-source provenance and identity-resolution semantics (electinfo's FEC cluster is the first such adopter). The pattern is three sibling **polymorphic supertypes** in `socialwarehouse.core`, each with its own subtype family:

| Supertype | Role | Subtypes | Status |
|---|---|---|---|
| `Agent` | Identity hub for actors | `Person`, `Committee`, `Organization` (domain-app detail rows) | Landed (SW#348) |
| `Event` | Canonicalization hub for events | `Transaction` (Contribution / Expenditure / Transfer / Obligation), and future siblings (election, disaster) | Planned (SW#349) |
| `Attestation` | Multi-source provenance / canonical-truth records | `FECAttestation` first; entity-resolution attestation a future sibling | Landed (SW#350) |

`core/` holds the polymorphic **bases only**; concrete subtype detail lives in the domain apps. This keeps the canonical-truth abstractions in one place while letting each domain own its specific columns.

### Agent supertype (SW#348)

`core.Agent` (table `sw_agent`) is the polymorphic actor hub. One Agent row is the canonical identity for an actor regardless of which concrete kind carries its detail:

- `subtype` — names the concrete kind (`person` / `committee` / `organization`); also the one-to-one reverse accessor on the Agent (`agent.person`, `agent.committee`, `agent.organization`).
- `lifecycle_state` — `active` / `dissolved` / `merged` / `unknown`.
- `resolution_confidence` — identity-resolution confidence in `[0, 1]`, NULL when unscored.
- `dissolved_on` — set when an agent dissolves.
- `entity_uuid` — deterministic UUID5 over `(subtype, data_source, source_record_id)` (via `IdentifiableModel`), so the same source row resolves to the same Agent on re-ingest.

Concrete subtypes inherit `core.AgentSubtype`, an abstract base that adds a **nullable** one-to-one `agent` link. `Person` is a new SW model; `Committee` and `Organization` gain the link without disturbing their existing tables. The link is nullable so the introducing migration is forward-only and backward-compatible — existing rows are valid unlinked and can be backfilled incrementally.

`Agent.get_subtype_instance()` dispatches on `subtype` to the matching detail row (or `None` when unlinked). This mirrors the electinfo `enterprise.agents` actor hub, where many incoming FKs target a single polymorphic actor id.

### Attestation supertype (SW#350)

`core.Attestation` (table `sw_attestation`) records multi-source-provenance observations of a canonical entity — "as of this source, parsed this way, the entity looked like this." Many attestations accumulate per entity (the electinfo FEC data carries hundreds per filing); the `is_canonical=True` row is the warehouse's current truth.

Polymorphic target without a Django `GenericForeignKey`:

- `entity_id` + `entity_subtype` — the attested entity's `entity_uuid` and its kind (`agent`, `committee`, `event`, `filing`, `address`, ...). `entity_subtype` is an open vocabulary; adopters attach attestations to their own kinds.
- `attestation_kind` — the subclass discriminator (`fec`, `entity_resolution`, ...).
- `attested_values` (JSON) + `attested_values_hash`, `attested_at`, `attested_by`, `attestation_source_tier`, `sequence`, `is_canonical`.
- `entity_uuid` (own artifact id) is a UUID4 — distinct from `entity_id` (the attested target). The two must not be confused.

A **partial unique constraint** (`uq_attestation_canonical_per_entity_kind`) enforces at most one canonical attestation per `(entity_id, entity_subtype, attestation_kind)`. Amendment is supersession: clear the old canonical, write a new canonical row at the next `sequence`.

Lookup helpers — `Attestation.for_entity(...)`, `Attestation.canonical_for(...)`, and `attestation.get_entity()` (resolves the target row via `ENTITY_SUBTYPE_MODELS`; raises `LookupError` for an unregistered kind) — give explicit, integrity-safe access in place of a GFK.

**`FECAttestation`** is the first concrete kind, a Django **multi-table-inheritance** child (table `sw_fec_attestation`) adding FEC-form provenance (`source_artifact_hash`, `source_artifact_id`, `parser_version`, `fec_form_type`, `fec_form_version`) and defaulting `attestation_kind` to `fec`. Future kinds (e.g. `EntityResolutionAttestation`) attach to the same superclass and may relocate to domain apps as the taxonomy grows.

### Attestation variant-linking shapes (SW#351)

Entity families link to `Attestation` in three different shapes, each shipped as an **abstract base class** in `core/`. SW ships no concrete subclass — adopters subclass per entity type in their own app, so there are no template-side tables or migrations.

| Base | Shape | When to use | Adopter example |
|---|---|---|---|
| `AttestationSubtypeLink` | `(attestation, entity_subtype, source_type)` | A polymorphic Attestation indexes a typed subtype detail row | `CommitteeAttestationLink` |
| `AttestationJunction` | `(entity_fk [adopter], attestation)` | Plain many-to-many: an entity has many attestations and vice versa | `FilingAttestationLink` |
| `ResolutionAttestation` | `raw_input` + `resolved_*` + `resolution_*` | The row records RAW input, the RESOLVED canonical target, and resolution metadata (status, confidence, resolver, run) | `AddressResolutionAttestation` |

The junction and subtype-link bases supply the `Attestation` FK (with a `%(class)s` reverse accessor); the adopter adds the entity side. `ResolutionAttestation` is the genuinely different shape — it is not "link entity to attestation" but "record how a raw input resolved to a canonical entity," with an `is_resolved` convenience property.

## Cross-references

- Initiative SW#284 (General Civic Ontology) — design doc: [`docs/designs/ontology.md`](designs/ontology.md).
- Initiative SW#250 (US Civic/Electoral template) — first initiative to be explicitly constrained by this principle.
- Sub-issue SW#251 design note (`sessions/260502-vital-channel/plans/think-sw251-person-model.md` in the workspace) — the canonical example of a warehouse-first design (v2 supersedes a v1 that was web-app-first).
- Per-initiative design notes: [`docs/designs/`](designs/).
- Contributor discipline: [`CONTRIBUTING.md`](../CONTRIBUTING.md).
