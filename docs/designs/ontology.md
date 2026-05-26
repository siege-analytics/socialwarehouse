# General Civic Ontology — Design

**Epic**: SW#284
**Tickets**: A-0 (#285) through A-9 (#294)
**Status**: Complete

## Problem

SocialWarehouse has strong geographic and demographic infrastructure (Delta Lake + PostGIS + Census ingest) but no canonical models for the actors, events, and financial flows that animate civic life. Questions like "who donated to which committee, in which election cycle, and what events was that committee involved in" require stitching together data from multiple external sources with no shared identity layer.

## Design principles

1. **Warehouse-first**: Delta schemas defined before PostGIS star schema, PostGIS before Django ORM. The web app is downstream.
2. **UUID-based agent linkage**: No FKs across app boundaries. Agents are identified by `entity_uuid` (UUID5 for identity entities, UUID4 for resolved artifacts). Cross-app queries join on UUID columns.
3. **Effective-dated temporality**: `effective_from`/`effective_to` on entities that change over time (classifications, roles, office terms). Enables "as-of" queries without SCD2 complexity at the Django layer.
4. **Event supertype with shared query surface**: All events (financial transactions, corporate events, redistricting, elections) are subtypes of a single `Event` model. `EventParticipant` bridges agents to events, enabling "all events involving Agent X" as a single query.
5. **SourceAwareModel mixin**: Every data-bearing model tracks its provenance (`data_source`, `jurisdiction_level`, `jurisdiction_state`, `source_record_id`, `ingested_at`).
6. **IdentifiableModel mixin**: Identity entities carry a `entity_uuid` field with `assign_uuid5()` / `assign_uuid4()` methods.

## Domain model

### Agents (A-2, A-3)

- **DimPerson** — warehouse dimension; lives in `socialwarehouse.warehouse`
- **Committee** — PAC, party committee, JFC. Entity-resolved by `entity_uuid`
- **Organization** — corporate entity with NAICS classification
- **Classification** — effective-dated type tags (PAC type, org sector, etc.)
- **Role** — effective-dated role assignments (treasurer, chair, agent)
- **Relationships** — 6 typed relationship models (simple, sponsor, control, subsidiary, corporate succession, DAF conduit)

### Political structure (A-4)

- **Office** — elected office (President, Governor, State Rep, etc.)
- **Seat** — specific seat within an office (e.g., TX HD-45)
- **Election** — election event (2024 General, 2026 Primary, etc.)
- **ElectoralContest** — specific race (TX HD-45 2024 General)
- **OfficeTerm** — who held which seat, when

### Transactions (A-5)

- **Contribution** — person/org → committee
- **Expenditure** — committee → vendor/org
- **Transfer** — committee → committee
- **Obligation** — stateful balance tracking (loan, payable)
- **ObligationEvent** — drawdown, repayment, forgiveness
- **TransactionGroup** — links multi-leg transactions (JFC distributions)

### Events (A-6)

- **Event** — supertype (SourceAwareModel)
- **EventParticipant** — bridge table (agent_uuid + role)
- **CorporateEvent** — merger, spinoff, acquisition, dissolution
- **SpatioTemporalEvent** — redistricting, annexation, boundary correction
- **ElectoralEvent** — certification, recount, contest resolution

### Plan-keyed boundaries (A-7)

- **PrecinctVTDIntersection** — pre-computed precinct/VTD overlaps by election cycle
- **Delta schemas**: `SILVER_REDISTRICTING_PLANS`, `SILVER_ADDRESS_BOUNDARY_PERIODS`, `SILVER_PRECINCT_VTD_INTERSECTIONS`

### API endpoints (A-8)

DRF read-only API for all ontology models. DefaultRouter + ReadOnlyModelViewSet pattern. Endpoints under `/api/agents/`, `/api/political/`, `/api/transactions/`, `/api/events/`.

## UUID strategy

| Entity type | UUID version | Generation |
|---|---|---|
| Person, Committee, Organization, Office, Seat | UUID5 | Deterministic from identity components via `generate_entity_uuid5()` |
| Transaction, Event, Obligation, ObligationEvent | UUID4 | Random via `generate_entity_uuid4()` |

UUID5 uses `SW_NAMESPACE = uuid5(NAMESPACE_URL, "socialwarehouse.siegeanalytics.com")` as the namespace. Input normalization: lowercase, strip whitespace, join with pipe separator.

## Delta Lake schemas

All schemas declared in `socialwarehouse/delta/tables.py` as PySpark `StructType`. Registered in the `TABLES` dict with path, schema, and partition_by. Silver-tier schemas added:

- `silver.contributions`, `silver.expenditures`, `silver.transfers`, `silver.obligations`
- `silver.events`, `silver.event_participants`, `silver.events_corporate`, `silver.events_spatiotemporal`, `silver.events_electoral`
- `silver.political_offices`, `silver.political_seats`, `silver.political_elections`, `silver.political_electoral_contests`, `silver.political_office_terms`
- `silver.redistricting_plans`, `silver.address_boundary_periods`, `silver.precinct_vtd_intersections`
