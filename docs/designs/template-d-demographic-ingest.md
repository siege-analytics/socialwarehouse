# Template-readiness D / SW#192 — Demographic ingest (design)

**Status:** Design v1. Awaiting maintainer answers on four open questions.

**Parent:** SW#189 (template-readiness initiative).
**Blocked by:** B (#190, done after #206).
**Partially blocked by:** C (#191) — `place` boundary needed for Phase 2; `puma` needed for Phase 3.

## Goal

Land a `socialwarehouse/demographic/` package that ingests ACS (American Community Survey) 1-year and 5-year estimates and decennial Census population data, keyed by boundary, queryable through F11-style helpers and exposed via the warehouse fact tables.

After D ships, an analyst can ask:
- "What's the median household income for tract 06037103300 in the ACS 2019-2023 vintage?"
- "How did the voting-age population of CD-06-12 change between the 2010 and 2020 Census?"
- "Which states' ACS 1-year tables have data for places with population <65K?" (none — that's the 5-year-only segment.)

## Architecture sketch

```
socialwarehouse/demographic/
    __init__.py
    models/
        __init__.py
        acs_estimate.py        # ACSEstimate, ACSVariable
        decennial_count.py     # DecennialCount, DecennialTable
    management/
        commands/
            load_acs.py        # python manage.py load_acs --vintage 2019-2023 --state 06
            load_decennial.py  # python manage.py load_decennial --year 2020 --state 06
    services/
        census_api.py          # thin client around census.gov ACS / Decennial APIs
        snapshot.py            # DimGeography.demographic_snapshot(vintage) helper
    migrations/
        0001_initial.py
```

## Models (Phase 1 sketch)

### ACSVariable

The published ACS variable catalog. Stable across vintages (mostly).

```python
class ACSVariable(models.Model):
    variable_code = models.CharField(max_length=20, unique=True, db_index=True)
    label = models.TextField()           # full hierarchical label
    table_code = models.CharField(max_length=20, db_index=True)  # e.g. "B01001"
    universe = models.CharField(max_length=255)
    concept = models.CharField(max_length=255)  # human-readable table name
```

Pre-seed with the most-used subset (B01001 population; B19013 median household income; etc.) via a `seed_acs_variables` command; full catalog importable on demand.

### ACSEstimate

The per-boundary per-vintage per-variable estimate.

```python
class ACSEstimate(models.Model):
    vintage = models.ForeignKey("sw_geo.Vintage", on_delete=models.CASCADE, limit_choices_to={"kind": "acs"})
    variable = models.ForeignKey(ACSVariable, on_delete=models.CASCADE)
    boundary_type = models.CharField(max_length=30, db_index=True)  # "state" / "county" / ...
    geoid = models.CharField(max_length=20, db_index=True)
    value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    moe = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    class Meta:
        unique_together = [["vintage", "variable", "boundary_type", "geoid"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["variable", "vintage", "boundary_type"]),
        ]
```

`boundary_type` is a CharField rather than a real FK to siege_utilities boundaries because:
- Different boundary types live in different tables (state vs county vs tract vs ...).
- A polymorphic FK (GFK) is awkward to query.
- The `(boundary_type, geoid)` shape is stable across all boundary types and matches how SW's `_BOUNDARY_TYPES` already keys things.

Trade-off: type-safety lost; can't do `estimate.county.name` directly — caller has to look up via `(boundary_type, geoid)`. Worth it for the cross-type queryability.

### DecennialCount / DecennialTable

Same shape as ACSEstimate but vintage is `census-decadal` and there's no MOE (decennial is a full count).

## Ingest path (Phase 1)

```
load_acs --vintage 2019-2023 --state 06 --tables B01001,B19013
  ↓
census_api.fetch_acs(vintage, state, tables, geo_levels)  # ACS API
  ↓
parsed rows
  ↓
ACSEstimate.objects.bulk_create(...)
```

Per-state per-vintage loads are bounded (a state has ~thousands of tracts; ACS API supports per-state queries efficiently). Idempotent: re-running clears+rewrites that (vintage, state, table) slice.

## Phasing

- **Phase 1:** ACS 5-year, ACSEstimate + ACSVariable models + load_acs command + a small variable catalog (B01001 population, B19013 median household income, B25001 housing units, B17001 poverty). Covers state / county / tract / block_group.
- **Phase 2:** ACS 1-year (places ≥65K population). Adds `place` boundary type dependency from C.
- **Phase 3:** Decennial Census (DecennialCount + DecennialTable + load_decennial). Adds `puma` boundary type dependency from C.

## Four open questions for the maintainer

### Q1. Variable catalog scope?

ACS publishes thousands of variables. Three options:
- (a) **Ship a small curated catalog** (~50 most-used variables: population, income, race, education, housing).
- (b) **Ship the full catalog as a fixture** (~30K rows).
- (c) **Ship empty; let users seed via `load_acs --table B01001`** which auto-creates variables on first reference.

**Recommendation: (a)** — small curated catalog as fixture, with the `load_acs` command's auto-creation path (option c) also available so users can extend.

### Q2. Estimate storage: long vs wide?

- (a) **Long (recommended in sketch above):** one row per (vintage, variable, boundary, geoid). Cross-variable comparison is a JOIN.
- (b) **Wide:** one row per (vintage, boundary, geoid) with hundreds of variable columns. Faster reads for "give me everything"; schema brittle when variables change between vintages.

**Recommendation: (a) long.** ACS variables change between releases (some retired, some added); wide format requires schema migrations per release. Long is more flexible at the cost of read-time JOINs (which materialized views or covering indexes can mitigate).

### Q3. API client: thin or feature-rich?

- (a) **Thin:** stdlib `urllib` + small JSON-shape helpers. No `census` Python package dependency.
- (b) **`census` Python package** (third-party): friendlier API, rate-limit awareness, retries.

**Recommendation: (b) `census` package.** Mature, maintained, handles rate limits + retries. Cost is one more dep. Pin a minimum version.

### Q4. Cross-vintage queries: explicit or helper?

ACS 2019-2023 is one vintage; ACS 2018-2022 is another; they overlap in source years but are different "as of" snapshots. Two ways callers compare across:
- (a) **Caller does it explicitly** — write the JOIN / aggregate by hand.
- (b) **Helper method** `DimGeography.demographic_timeseries(variable, geoid, boundary_type)` that returns a list of (vintage, value, moe) over time.

**Recommendation: (b) helper.** "How did income change over time" is THE killer demographic query; the helper makes it discoverable. Same pattern as F11's `boundary_timeline`.

## Out of scope (for this PR / sub-issue)

- ACS public-use microdata (PUMS). Aggregate-table-only.
- Decennial detailed sample (long-form replaced by ACS in 2010+).
- ACS variable curation for analyst use (template ships a default subset; users add their own).
- Cross-source harmonization (e.g., reconciling ACS estimates against Decennial counts).

## Sequencing

- This PR (design v1) → maintainer Q1-Q4 → Phase 1 implementation PR → Phase 2 / Phase 3 implementation PRs (in priority order).

## References

- Parent: SW#189
- B PR #2 (just merged): #206 (Vintage model is now the canonical FK target)
- C design (open): #207 (boundary catalog; `place` and `puma` come from there)
- Census ACS API: api.census.gov/data/2023/acs/acs5
- `census` Python package: census.readthedocs.io
