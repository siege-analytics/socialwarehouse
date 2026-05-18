# DimGeography (Django model, socialwarehouse.warehouse.models)

**Definition:** `socialwarehouse/warehouse/models/dimensions.py:12`
**Surveyed at:** 2026-05-18
**Owner:** warehouse maintainers

## Shape

### Fields

| Field | Type | Notes |
|---|---|---|
| `geoid` | CharField(max_length=20) | db_index; Census GEOID (e.g. "06037") |
| `name` | CharField(max_length=255) | |
| `vintage_year` | PositiveSmallIntegerField | db_index; validated 1790-2100 |
| `summary_level` | CharField(max_length=30) | db_index; state/county/tract/blockgroup/place/cd/zcta |
| `state_fips` | CharField(max_length=2) | db_index; blank=True default="" |
| `geometry` | MultiPolygonField(srid=4326) | nullable |
| `area_land` | BigIntegerField | nullable; sq meters |
| `area_water` | BigIntegerField | nullable; sq meters |
| `internal_point` | PointField(srid=4326) | nullable; interior label point |
| `parent` | ForeignKey(self) | SET_NULL; related_name="children"; for drill-up |
| `effective_from` | DateField | nullable; SCD2 validity start |
| `effective_to` | DateField | nullable; NULL = current |
| `is_current` | BooleanField(default=True) | db_index; latest-version flag |
| `created_at` | DateTimeField(auto_now_add=True) | |
| `updated_at` | DateTimeField(auto_now=True) | |

### Constraints

- Surrogate PK: BigAutoField (auto)
- `unique_together = [("geoid", "vintage_year")]` — natural key
- Indexes: `(summary_level, vintage_year)`, `(state_fips, summary_level)`, `(is_current, summary_level)`

### Lookups callers rely on

- `DimGeography.objects.filter(is_current=True)` — current-version filtering (used by ViewSet)
- `DimGeography.objects.filter(geoid__startswith=state_fips)` — state-scoped queries
- `parent` reverse: `geo.children.all()` — drill-down

## Callers / consumers

- `socialwarehouse/api/warehouse/views.py:DimGeographyViewSet` — read-only API surface
- `socialwarehouse/api/warehouse/serializers.py:DimGeographySerializer` — serialization
- `socialwarehouse/warehouse/services/dimension_loader.py` — ETL loader
- FactElectionResult, FactACSEstimate, FactRedistrictingPlan — FK target

## Cross-references

- **Self-FK:** `parent` for hierarchical drill-up.
- **Referenced by:** FactElectionResult.geography, FactACSEstimate.geography, FactRedistrictingPlan.geography.

## Known assumptions / gotchas

- **SCD Type 2** — multiple rows per (geoid) across vintage years; use `is_current=True` when you want today's boundary.
- **geometry is nullable** — lightweight loads skip it. Code paths that assume geometry exists must filter `geometry__isnull=False`.
- **state_fips defaults to ""** not None — `filter(state_fips="")` returns the unset rows; `filter(state_fips__isnull=True)` returns nothing.

## Survey log

- 2026-05-18: Seeded from live model. PR #105 added SCD2 fields (effective_from/to, is_current). PR #106 cleared field-name mismatch with loader (DimRedistrictingCycle, not this model — listed here only as related context).
