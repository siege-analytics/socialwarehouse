# DimTime (Django model, socialwarehouse.warehouse.models)

**Definition:** `socialwarehouse/warehouse/models/dimensions.py:218`
**Surveyed at:** 2026-05-18
**Owner:** warehouse maintainers

## Shape

### Fields

| Field | Type | Notes |
|---|---|---|
| `calendar_date` | DateField | unique=True |
| `year` | PositiveSmallIntegerField | db_index |
| `quarter` | PositiveSmallIntegerField | 1-4 |
| `month` | PositiveSmallIntegerField | 1-12 |
| `day_of_year` | PositiveSmallIntegerField | |
| `day_of_month` | PositiveSmallIntegerField | 1-31; default=1 |
| `day_of_week` | PositiveSmallIntegerField | 0-6; Python weekday() (0=Mon, 6=Sun); default=0 |
| `week_of_year` | PositiveSmallIntegerField | 1-53 (ISO); default=1 |
| `is_census_day` | BooleanField(default=False) | April 1 of decennial years |
| `is_election_day` | BooleanField(default=False) | first Tue after first Mon in November |
| `is_presidential_election` | BooleanField(default=False) | db_index |
| `is_midterm_election` | BooleanField(default=False) | db_index |
| `federal_fiscal_year` | PositiveSmallIntegerField(default=0) | FY starts Oct 1 of (calendar_year - 1) |
| `created_at` | DateTimeField(auto_now_add=True) | |

### Constraints

- Surrogate PK: BigAutoField
- `calendar_date` is unique (natural key)
- Indexes: `(year, quarter)`, `(is_census_day,)`, `(is_election_day,)`

### Lookups callers rely on

- `DimTime.objects.filter(calendar_date=...)` — point lookups
- `DimTime.objects.filter(year=..., quarter=...)` — quarterly facts
- `DimTime.objects.filter(is_election_day=True)` — election joins

## Callers / consumers

- `socialwarehouse/warehouse/services/dimension_loader.py:_load_time` — date-range backfill
- Fact tables that join on time (election results, ACS by year)

## Cross-references

- No FKs out.
- Referenced by fact tables via `time` FK convention (not enforced at this model — fact tables declare their own FK).

## Known assumptions / gotchas

- **`day_of_week` is Python convention** (0=Monday), NOT ISO 8601 (1=Monday) or US convention (1=Sunday). Loaders that use other libraries' weekday conventions misalign.
- **`federal_fiscal_year` defaults to 0** for unset. Filters on `federal_fiscal_year=2026` won't return seed rows that haven't been backfilled. Update_or_create paths must set this explicitly.
- **The loader bug PR #105 fixed** wrote keys (`day_suffix`, `day_name`, etc.) that aren't on this model. The fields above are the *only* fields a `defaults={...}` dict may use. If you add new fields, update this page in the same PR.

## Survey log

- 2026-05-18: Seeded from live model. PR #105 extended schema with day_of_month, day_of_week, week_of_year, is_presidential_election, is_midterm_election, federal_fiscal_year — these match this page's listing.
