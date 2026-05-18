# DimRedistrictingCycle (Django model, socialwarehouse.warehouse.models)

**Definition:** `socialwarehouse/warehouse/models/dimensions.py:290`
**Surveyed at:** 2026-05-18
**Owner:** warehouse maintainers

## Shape

### Fields

| Field | Type | Notes |
|---|---|---|
| `cycle_year` | PositiveSmallIntegerField | unique=True; validated 1960-2040 |
| `census_year` | PositiveSmallIntegerField(default=0) | renamed from `decennial_census_year` in PR #106 |
| `first_election_year` | PositiveSmallIntegerField(default=0) | typically cycle_year + 2 |
| `effective_start` | DateField | nullable; cycle's effective period start |
| `effective_end` | DateField | nullable; end of effective period |
| `notes` | TextField(blank=True, default="") | |
| `created_at` | DateTimeField(auto_now_add=True) | |

### Constraints

- Surrogate PK: BigAutoField
- `cycle_year` is unique
- No additional indexes declared.

### Lookups callers rely on

- `DimRedistrictingCycle.objects.get(cycle_year=2020)` — direct lookup
- `update_or_create(cycle_year=YEAR, defaults={"census_year": ..., "first_election_year": ..., "effective_start": ..., "effective_end": ..., "notes": ...})` — loader pattern

## Callers / consumers

- `socialwarehouse/warehouse/services/dimension_loader.py` — ETL
- FactRedistrictingPlan — FK target

## Cross-references

- Referenced by FactRedistrictingPlan via `cycle` FK.

## Known assumptions / gotchas

- **`census_year` NOT `decennial_census_year`** — the original loader used the longer name and W2/#106 fixed it. Any new caller writing `decennial_census_year=` will fail with FieldError. The static scanner at claude-configs-public#117 catches this for same-file callers; cross-file callers rely on this doc page.
- **`first_election_year` is typically cycle_year + 2** but loaders should compute it explicitly — not all cycles follow the pattern (special elections, mid-decade redistricting).
- **`effective_start` / `effective_end` are nullable** but production rows always have them set; nullable is for backfill convenience. Query callers should not assume non-null.

## Survey log

- 2026-05-18: Seeded from live model post-PR #106 fix.
- Pre-PR-#106: schema had `decennial_census_year` instead of `census_year`; loader's `defaults={...}` dict referenced `census_year` causing FieldError. Fixed in PR #106 by renaming the model field (loader code was correct).
