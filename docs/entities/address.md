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

- `socialwarehouse/geo/management/commands/geocode_addresses.py` — bulk geocoding; calls `assign_census_units_from_fips` + `addr.save()` per address (M2 / SW#146 — should bulk_update).
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
- **Per-row `.save()` in geocode loop** is the M2 bottleneck — see SW#146.

## Survey log

- 2026-05-18: Seeded from live model. F3/M2/M6 surfaced in E1 review (SW#92, #146, #150).
