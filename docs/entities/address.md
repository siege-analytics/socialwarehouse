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

- `assign_census_units_from_fips(state_fips, county_fips, tract, block)` — constructs hierarchical GEOIDs from Census Geocoder FIPS output. Mutates instance fields; caller must `.save()`.
- `populate_foreign_keys()` — populates siege_geo FK refs from GEOIDs.

## Callers / consumers

- `socialwarehouse/geo/management/commands/geocode_addresses.py` — bulk geocoding. Post-M1+M2+M3 fix (SW#145+#146+#147): streams via `qs.iterator(chunk_size=batch_size)`, accumulates per-chunk updates, flushes via `Address.objects.bulk_update(pending, ADDRESS_BULK_UPDATE_FIELDS, batch_size=500)`. No `qs.count()` before iteration; no per-row `.save()`; no full materialization before the geocoder API call.
- `socialwarehouse/geo/management/commands/assign_boundaries.py` — bulk boundary assignment.
- `socialwarehouse/geo/management/commands/export_to_delta.py` — exports to bronze tier.
- API: addresses are not directly exposed via REST (no AddressViewSet at time of survey).

## Cross-references

- No declared FKs on Address itself; GEOIDs are string-keyed against siege_utilities geo models (see DemographicSnapshot doc for the geoid-as-string-key pattern).
- `populate_foreign_keys()` lazily wires FK relations to siege_utilities boundary models — not part of the schema; runtime hydration.

## Known assumptions / gotchas

- **`null=True` on CharField throughout** is a Django-convention violation (F3 / SW#92): Django convention is `blank=True, default=""`, not `null=True`. The model uses the latter everywhere. Means `filter(field="")` and `filter(field__isnull=True)` return different sets; callers must know which case the data is in.
- **`geocoded=True` does NOT imply `geom` is set.** M6 / SW#150: matched-without-coords sets `geocoded=True` with `geom=NULL`. Filter `geocoded=True AND geom__isnull=False` if you need both.
- **`geocode_source` values are free-form strings** (not a choices field). Known values: "census", "nominatim". Add a CHOICES list if a third source appears.
- **Per-row `.save()` in geocode loop** was the M2 bottleneck (SW#146). FIXED: `geocode_addresses.py` now uses `Address.objects.bulk_update(pending, ADDRESS_BULK_UPDATE_FIELDS, batch_size=500)`. Future bulk-update callers should mirror this pattern: maintain a `pending_updates` list, flush per chunk, name the field list explicitly so only intended fields are written.
- **`qs.count()` followed by `.iterator()` re-executes the SELECT.** Was M1 (SW#145), fixed. Don't reintroduce a pre-iteration count in the same flow; for advisory counts use the dry-run code path only.
- **Materializing all addresses before a chunked API call defeats the chunking.** Was M3 (SW#147), fixed. The new `_yield_chunks` generator + `qs.iterator(chunk_size=...)` caps memory at O(chunk_size). Reusable shape for other bulk loaders.

## Survey log

- 2026-05-18: Seeded from live model. F3/M2/M6 surfaced in E1 review (SW#92, #146, #150).
- 2026-05-18: M1+M2+M3 bundled fix shipped — `geocode_addresses.py` rewritten to stream addresses via `qs.iterator(chunk_size=batch_size)`, accumulate per-chunk updates, flush via `Address.objects.bulk_update`. ADDRESS_BULK_UPDATE_FIELDS constant + `_yield_chunks` generator added. Callers wanting the same pattern can reference geocode_addresses.py:handle().
