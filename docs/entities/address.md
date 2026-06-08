# Address (Django model, socialwarehouse.geo.models)

**Definition:** `socialwarehouse/geo/models/address.py:19`
**db_table:** `sw_geo_address`
**Surveyed at:** 2026-05-18
**Owner:** geo maintainers

## Shape

### Fields (grouped)

**USPS / address components**
- `primary_number`, `street_name`, `street_suffix`, `city_name`, `default_city_name`, `state_abbreviation` (max 2), `zip5` / `zip4` (TODO confirm exact name), `delivery_point`, `delivery_point_check_digit`, `record_type`, `zip_type`, `county_fips`, `county_name`, `carrier_route`, `congressional_district`, `rdi`, `elot_sequence`, `elot_sort` — all CharField(max_length=250), `null=True, blank=True, default=None` (Django-convention violation; see F3 / SW#92).

**Coordinates**
- `latitude`, `longitude` — DecimalField(max_digits=22, decimal_places=16), nullable
- `geom` — PointField(srid=4326), nullable
- `coordinate_license`, `precision`, `time_zone`, `utc_offset` — CharField, nullable

**Geocoding state**
- `geocoded` — BooleanField(default=False)
- `geocode_quality` — CharField, nullable
- `geocode_source` — CharField, nullable (values used: "census", "nominatim")
- `geocoded_at` — DateTimeField, nullable

**Census unit assignments**
- `census_year` — IntegerField, db_index'd
- `state_geoid` (2), `county_geoid` (5), `tract_geoid` (11), `block_group_geoid` (12), `block_geoid` (15), `vtd_geoid` (11), `cd_geoid` (4), `sldl_geoid`, `sldu_geoid`
- `census_units_assigned_at` — DateTimeField, nullable

### Constraints

- Surrogate PK: BigAutoField (auto)
- No unique_together
- Indexes (10): see Meta block; covers most common filter pairs (state+city, county_fips, cd_district, census_year, geocoded, state+county_geoid, plus year-scoped indexes for cd/vtd/sldl/sldu GEOIDs).

### Methods of interest

- `assign_census_units_from_fips(state_fips, county_fips, tract, block)` — constructs hierarchical GEOIDs from Census Geocoder FIPS output. Mutates instance fields; **caller must `.save()`**.
- `populate_foreign_keys()` — populates siege_geo FK refs from GEOIDs. Post-F4/F5 (SW#93+#94): mutates instance fields and returns `self`; **caller must `.save()`** (matches `assign_census_units_from_fips`). Pre-fix it called `self.save()` internally — asymmetric with the other instance-mutating method and a hidden per-call write that was suboptimal in bulk-update flows.

### Module constants

- `DEFAULT_CENSUS_YEAR = 2020` — single edit site for the model's `census_year` field default. Bumped manually each decade. Path-of-least-resistance fix for F6 (SW#95) — a `CensusVintageConfig`-driven callable default tangles with F11 (SW#100, still open) and is deferred until that question is settled.

## Callers / consumers

- `socialwarehouse/geo/management/commands/geocode_addresses.py` — bulk geocoding. Post-M1+M2+M3 fix (SW#145+#146+#147): streams via `qs.iterator(chunk_size=batch_size)`, accumulates per-chunk updates, flushes via `Address.objects.bulk_update(pending, ADDRESS_BULK_UPDATE_FIELDS, batch_size=500)`. No `qs.count()` before iteration; no per-row `.save()`; no full materialization before the geocoder API call.
- `socialwarehouse/geo/management/commands/assign_boundaries.py` — bulk boundary assignment.
- `socialwarehouse/geo/management/commands/export_to_delta.py` — exports to bronze tier.
- API: addresses are not directly exposed via REST (no AddressViewSet at time of survey).

## Cross-references

- No declared FKs on Address itself; GEOIDs are string-keyed against siege_utilities geo models (see DemographicSnapshot doc for the geoid-as-string-key pattern).
- `populate_foreign_keys()` lazily wires FK relations to siege_utilities boundary models — not part of the schema; runtime hydration.

## Known assumptions / gotchas

- **CharFields use `blank=True, default=""` per Django convention** (post-F3/SW#92). Pre-fix all 29 text fields used `null=True, blank=True, default=None`; post-fix the column is NOT NULL with `""` as the canonical "not yet set / unknown" value. Filter contract: use `field=""` or `exclude(field="")` instead of `__isnull=True`/`__isnull=False`. The 3 caller sites in `warehouse/services/geographic_enrichment.py` that used `tract_geoid__isnull=False` were updated in the same PR to `tract_geoid__gt=""`. `latitude`/`longitude`/`geom` stay nullable — numeric NULL is the canonical "unknown" for those types.
- **`geocoded=True` implies `geom IS NOT NULL`** (post-M6/SW#150 fix). Pre-fix Census's `matched=True` flipped `geocoded=True` even when lat/lon were unpopulated, leaving `geom=NULL`; post-fix Phase 1 requires both coords before setting `geocoded=True` and demotes matched-without-coords to the unmatched bucket for Phase 2 (Nominatim) to retry. Downstream filters on `geocoded=True` alone are now safe.
- **`geocode_source` has `choices=` post-F7/SW#96.** Canonical values lowercase per `GEOCODE_SOURCE_CHOICES` (`census`, `nominatim`, `google`, `smartystreets`). The choices add is metadata-only — existing rows with non-canonical values (legacy data) are preserved; only new admin-form writes are constrained. To add a new geocoder, append to the module constant and ship a migration. `geocode_quality` and `precision` were NOT given `choices=` in F7: `geocode_quality` has historically been written as full address strings (not categorical), so the help_text's enumeration is aspirational; `precision` has no writers in the SW codebase and no values to enumerate.
- **Per-row `.save()` in geocode loop** was the M2 bottleneck (SW#146). FIXED: `geocode_addresses.py` now uses `Address.objects.bulk_update(pending, ADDRESS_BULK_UPDATE_FIELDS, batch_size=500)`. Future bulk-update callers should mirror this pattern: maintain a `pending_updates` list, flush per chunk, name the field list explicitly so only intended fields are written.
- **`qs.count()` followed by `.iterator()` re-executes the SELECT.** Was M1 (SW#145), fixed. Don't reintroduce a pre-iteration count in the same flow; for advisory counts use the dry-run code path only.
- **Materializing all addresses before a chunked API call defeats the chunking.** Was M3 (SW#147), fixed. The new `_yield_chunks` generator + `qs.iterator(chunk_size=...)` caps memory at O(chunk_size). Reusable shape for other bulk loaders.

## Survey log

- 2026-05-18: Seeded from live model. F3/M2/M6 surfaced in E1 review (SW#92, #146, #150).
- 2026-05-18: M1+M2+M3 bundled fix shipped — `geocode_addresses.py` rewritten to stream addresses via `qs.iterator(chunk_size=batch_size)`, accumulate per-chunk updates, flush via `Address.objects.bulk_update`. ADDRESS_BULK_UPDATE_FIELDS constant + `_yield_chunks` generator added. Callers wanting the same pattern can reference geocode_addresses.py:handle().
- 2026-05-19: M6 / SW#150 — Phase 1 now requires `matched AND lat AND lon` before flipping `geocoded=True`; matched-without-coords demoted to Phase 2 (Nominatim) for a real try. The `geocoded=True implies geom IS NOT NULL` invariant downstream code relies on is now load-bearing.
- 2026-05-19: F4 + F5 / SW#93 + #94 — `populate_foreign_keys()` no longer silently saves. It mutates the instance and returns `self`; caller is responsible for `.save()` (matches `assign_census_units_from_fips`). Updated the only caller (`assign_boundaries.py`) to call `populate_foreign_keys()` BEFORE its existing `.save()` so the geoid changes and the FK assignments share a single UPDATE.
- 2026-05-19: F6 / SW#95 — Hoisted `census_year` default to module constant `DEFAULT_CENSUS_YEAR = 2020`. Single edit site for the manual-per-decade bump. Callable default (reading `CensusVintageConfig`) deferred until F11 / SW#100 is settled.
- 2026-05-19: F9 / SW#98 — `assign_boundaries.py` method-local-imports pattern documented at module top: Django AppRegistryNotReady avoidance (management commands import before app loader is ready), heavyweight boundary-model cost-of-import for unrelated commands, and conditional plan-aware code paths.
- 2026-05-19: F7 / SW#96 fix — `geocode_source` gained `choices=` keyed to module constant `GEOCODE_SOURCE_CHOICES` (lowercase: census, nominatim, google, smartystreets). Migration `0002_address_geocode_source_choices.py` is metadata-only (no data validation against existing rows). `geocode_quality` and `precision` deferred from F7 with explicit rationale (vendor surface writes full address strings to geocode_quality; precision has no writers).
- 2026-05-19: F3 / SW#92 — sweep `null=True` off all 29 Address CharFields. Pre-fix `null=True, blank=True, default=None`; post-fix `blank=True, default=""` (Django convention). Migration `0003_address_charfield_null_to_blank_default.py` is two-phase: data backfill (`UPDATE ... SET <field> = '' WHERE <field> IS NULL`) then AlterField for each field. Caller updates in same PR: 3 sites in `warehouse/services/geographic_enrichment.py` changed from `tract_geoid__isnull=False` to `tract_geoid__gt=""` (post-fix the `__isnull` form matches every row because the column is NOT NULL). One test assertion in `tests/unit/geo/test_models.py` updated from `is None` to `== ""`.
