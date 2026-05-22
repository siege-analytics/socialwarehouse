# Boundary catalog

The set of geographic boundary types that SW addresses are cached against and that `AddressBoundaryPeriod` (ABP) rows are keyed by. Each type is a field on `AddressBoundaryPeriod` (`{type}_geoid`) and a cache field on `Address` (`{type}_geoid`); F11's read-side helpers (`boundary_history`, `boundary_on`, `boundaries_on`, `boundary_timeline`) operate uniformly across every type listed in `Address._BOUNDARY_TYPES`.

This doc is the single source of truth for what types exist, what each one keys on, what populates it, and how it lines up with the four template-readiness domains (political / demographic / economic / civic) under SW#189.

## Schema invariant

For every type in `Address._BOUNDARY_TYPES`:

- `Address.{type}_geoid` is the cache field on the latest-effective ABP row.
- `AddressBoundaryPeriod.{type}_geoid` is the per-row authoritative value.
- `addr.boundary_timeline("<type>")` returns the time-ordered ABP rows for that type.
- `addr.boundary_on("<type>", date)` returns the row covering that date.

The cache field is operational (fast read for "what's the current value"); the ABP rows are authoritative (preserves history across vintage boundaries). The two are kept in sync by signal-driven cache refresh per F11 step 2b (SW#100).

## Catalog

### Political (electoral / redistricting)

| Type | GEOID format | Length | Source | Vintage shape | Ingest |
|---|---|---|---|---|---|
| `state` | 2-digit FIPS | 2 | Census | census-decadal | TIGER fetch |
| `county` | 5-digit FIPS (state+county) | 5 | Census | census-decadal | TIGER fetch |
| `vtd` | state+county+VTD | 11 | Census | census-decadal | TIGER fetch |
| `cd` | state+CD number | 4 | Census + redistricting plan | redistricting-plan (per-plan vintage; can re-key intra-decade) | TIGER fetch + plan-aware reassignment |
| `sldl` | state+SLDL | 5 | Census + redistricting plan | redistricting-plan | TIGER fetch + plan-aware reassignment |
| `sldu` | state+SLDU | 5 | Census + redistricting plan | redistricting-plan | TIGER fetch + plan-aware reassignment |

The three redistricted types (`cd`, `sldl`, `sldu`) carry per-plan vintage so a court-ordered mid-decade redistricting produces a new ABP row without invalidating the prior plan's assignments. See `dim_redistricting_cycle.md`.

### Census-administrative (geographic units used across domains)

| Type | GEOID format | Length | Source | Vintage shape | Ingest |
|---|---|---|---|---|---|
| `tract` | state+county+tract | 11 | Census | census-decadal | TIGER fetch |
| `block_group` | state+county+tract+BG | 12 | Census | census-decadal | TIGER fetch |
| `block` | state+county+tract+block | 15 | Census | census-decadal | TIGER fetch |
| `zcta` | 5-digit ZCTA (Census-derived) | 5 | Census ZCTAs | census-decadal | TIGER fetch (per SW#191 high-priority batch) |
| `place` | state+place FIPS | 7 | Census Places (CDP + incorporated) | census-decadal | TIGER fetch (per SW#191 high-priority batch) |

Note on `zcta` vs `Address.zip5`: ZCTA is the Census-derived 5-digit approximation of a ZIP for geographic analysis; `zip5` is the postal ZIP as written on the envelope. They usually match but diverge for PO boxes, military APO/FPO addresses, and edge cases. Economic ingest (IRS SOI, FCC broadband) keys on `zcta_geoid`; mail-handling logic keys on `zip5`.

### Economic

| Type | GEOID format | Length | Source | Vintage shape | Ingest |
|---|---|---|---|---|---|
| `cbsa` | 5-digit CBSA code | 5 | Census/OMB CBSA delineation | census-decadal (OMB-cadence drift accepted in v1; see SW#191 design Q4) | OMB delineation files (per SW#193 BLS QCEW + IRS SOI ingest) |

CBSAs are the standard geography for BLS and BEA economic statistics. Currently using `census-decadal` vintage; if CBSAs become operationally awkward against the decadal vintage cadence, add a `cbsa-omb` vintage kind (one-row addition to `Vintage.KIND_CHOICES` + subclass + migration).

### Demographic

| Type | GEOID format | Length | Source | Vintage shape | Ingest |
|---|---|---|---|---|---|
| `puma` | state+PUMA | 7 | Census PUMAs | census-decadal | TIGER fetch (per SW#191 medium-priority batch; per SW#192 D Phase 2 for ACS PUMS) |
| `urban_area` | UA code | 5 | Census UA delineation | census-decadal | TIGER fetch (per SW#191 medium-priority batch) |

### Civic

| Type | GEOID format | Length | Source | Vintage shape | Ingest |
|---|---|---|---|---|---|
| `school_district` | state+SD (unified / elementary / secondary collapsed) | 7 | Census + NCES | nces-school-year (per the polymorphic Vintage from SW#190 B) | NCES fetch (per SW#194 F Phase 1) |
| `fire_district` | state+SD | 7 | Census Special Districts | census-decadal | Census SD fetch (per SW#194 F Phase 2) |
| `water_district` | state+SD | 7 | Census Special Districts | census-decadal | Census SD fetch (per SW#194 F Phase 2) |
| `hospital_district` | state+SD | 7 | Census Special Districts | census-decadal | Census SD fetch (per SW#194 F Phase 2) |
| `library_district` | state+SD | 7 | Census Special Districts | census-decadal | Census SD fetch (per SW#194 F Phase 2) |
| `cemetery_district` | state+SD | 7 | Census Special Districts | census-decadal | Census SD fetch (per SW#194 F Phase 2) |
| `mosquito_district` | state+SD | 7 | Census Special Districts | census-decadal | Census SD fetch (per SW#194 F Phase 2) |
| `other_special_district` | state+SD | 7 | Census Special Districts (residual category) | census-decadal | Census SD fetch (per SW#194 F Phase 2) |

Per SW#191 design Q2: special districts are broken out per kind (7 separate cache fields + ABP columns + tuple entries) rather than collapsed into one `special_district` type with a `kind` discriminator. An address is often in multiple special districts simultaneously (e.g., a fire AND a water district both cover the same address); the per-kind shape gives each its own cache field rather than overloading one. The residual `other_special_district` catches kinds not yet broken out.

## Reading the catalog

- **By F11 helper**: any helper accepts any type in `_BOUNDARY_TYPES`. `addr.boundary_timeline("zcta")` works identically to `addr.boundary_timeline("state")`.
- **By ingest**: TIGER fetch (`scripts/fetch_census_tiger.py`) populates the geographic-only types; ACS / QCEW / NCES / Special-Districts fetches populate domain-specific types per their sub-issues under SW#189 D / E / F.
- **By vintage**: each type carries one vintage shape (census-decadal, redistricting-plan, nces-school-year). The polymorphic Vintage model (SW#190) discriminates kinds; each ABP row points at the appropriate vintage instance for its type.

## Cross-references

- `Address.boundary_timeline` / `boundary_on` / `boundaries_on` / `boundary_history`: F11 read helpers — `socialwarehouse/geo/models/address.py`
- `_BOUNDARY_TYPES` tuple: `socialwarehouse/geo/models/address.py:413`
- F11 design v2.2: `docs/designs/f11-address-temporal-boundary-history.md`
- Template-readiness C design: `docs/designs/template-c-boundary-catalog.md`
- Vintage polymorphization (B): `docs/designs/template-b-vintage-polymorphization.md`
- Ingest packages: `docs/designs/template-d-demographic-ingest.md`, `template-e-economic-ingest.md`, `template-f-civic-ingest.md`
- Address entity: `docs/entities/address.md`
- Redistricting cycle: `docs/entities/dim_redistricting_cycle.md`

## Adding a new boundary type

1. Pick the type name (`<type>`), its GEOID format, and its vintage shape.
2. Add `Address.{type}_geoid` CharField.
3. Add `AddressBoundaryPeriod.{type}_geoid` CharField.
4. Add `"<type>"` to `Address._BOUNDARY_TYPES` tuple.
5. Add Django migration (`makemigrations geo`).
6. Add F11-helper integration test verifying `boundary_timeline("<type>")` returns the new type's rows.
7. Update this catalog with a row for the new type.
8. If the type needs a new vintage kind not in `Vintage.KIND_CHOICES`, add it (B's polymorphic Vintage supports this).

The pattern is mechanical; the longest tail is the ingest path (which is the responsibility of the appropriate domain sub-issue under SW#189, not this catalog).
