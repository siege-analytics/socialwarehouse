# M5 / SW#149 — PostGIS-side ST_Intersection rewrite (design)

**Status**: Design. No code in this PR. Awaiting maintainer sign-off before the implementation PR opens.

## Problem

`socialwarehouse/geo/management/commands/compute_geographic_intersections.py` computes county-CD and VTD-CD intersections with a Python-side nested loop:

```python
for county in counties.iterator():
    cds = CongressionalDistrict.objects.filter(
        vintage_year=year,
        geom__intersects=county.geom,
    )
    for cd in cds:
        intersection_geom = county.geom.intersection(cd.geom)  # round-trip to Python
        ...
```

Every `(county × intersecting-CD)` pair pulls geometries from PostGIS into Python, computes the intersection in GEOS, computes the area, then writes back via `update_or_create`. For a national-scale dataset (3,100 counties × ~5 intersecting CDs each + 200K+ VTDs × CDs), this is the cron's expensive step.

## Goal

Replace the per-pair Python loop with one (or two — one per intersection type) `INSERT ... SELECT ... ST_Intersection ... ON CONFLICT ... DO UPDATE` statement(s). Computation stays in PostgreSQL; Python only orchestrates and reports.

## Three real footguns (must resolve before code lands)

### 1. siege_geo db_table introspection

`CountyCongressionalDistrictIntersection` FKs to `siege_geo.County` and `siege_geo.CongressionalDistrict`. The `db_table` for those is set by the `CensusTIGERBoundary` base class in `siege_utilities`. SW code only sees the Python class name; the underlying table name isn't trivially visible from this repo's surface.

**Resolution path**: introspect at runtime via Django's app registry inside the management command:

```python
County._meta.db_table  # → e.g. "geo_county"
CongressionalDistrict._meta.db_table  # → e.g. "geo_congressional_district"
VTD._meta.db_table  # → e.g. "political_vtd"
```

Use those in the dynamic SQL. Pin the values in a startup-time assertion (compare against an `EXPECTED_TABLES` dict per SU version) so an upstream rename surfaces immediately rather than silently writing to the wrong table.

### 2. SRID reconciliation

`CountyCongressionalDistrictIntersection.intersection_geom` is `MultiPolygonField(srid=4269)`.
siege_geo's `County.geom` and `CongressionalDistrict.geom` — needs verification. Two reasonable possibilities:
- 4326 (TIGER's geographic default for newer pipelines)
- 4269 (NAD83, TIGER/Line's native — most common)

**Resolution path**: read the field definitions in `siege_utilities/geo/django/models/boundaries.py` and `political.py` to confirm. If 4326, the SQL needs `ST_Transform(c.geom, 4269)` on both sides of the intersection AND consistent area calculations in the target SRID. If 4269, no transform needed.

The intersection_geom field has SRID 4269; ST_Intersection produces output in the input SRID, so the output already matches. Area computation should use `ST_Area(ST_Transform(intersection_geom, <projected_SRID>))` (e.g. EPSG:5070 for CONUS) for meaningful square-meter values — the existing Python code uses `geom.area` which returns degrees-squared in 4326/4269. **Verify this is the existing bug or feature** before preserving it.

### 3. `ON CONFLICT (...) DO UPDATE` constraint match

`Meta.unique_together = [["siege_county", "siege_cd", "year"]]` generates a unique index whose default name is auto-derived by Django. The `ON CONFLICT (...)` SQL needs to target the constraint by name OR by columns.

**Resolution path**: target by columns:

```sql
ON CONFLICT (siege_county_id, siege_cd_id, year)
DO UPDATE SET
    intersection_geom = EXCLUDED.intersection_geom,
    intersection_area_sqm = EXCLUDED.intersection_area_sqm,
    pct_of_county = EXCLUDED.pct_of_county,
    pct_of_cd = EXCLUDED.pct_of_cd,
    relationship = EXCLUDED.relationship,
    is_dominant = EXCLUDED.is_dominant
```

Column-based `ON CONFLICT` is portable across PG versions and doesn't depend on Django's constraint naming. Pin the column list against the model fields (introspect via `._meta.unique_together`) at command startup so a future model change surfaces a clear error rather than a silent fallthrough.

## Proposed SQL shape (county-CD)

```sql
INSERT INTO sw_geo_intersection_county_cd (
    siege_county_id, siege_cd_id, year,
    intersection_geom, intersection_area_sqm,
    pct_of_county, pct_of_cd,
    relationship, is_dominant,
    computed_at
)
SELECT
    c.id AS siege_county_id,
    d.id AS siege_cd_id,
    %s AS year,
    ST_Multi(ST_Intersection(c.geom, d.geom)) AS intersection_geom,
    CAST(ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) AS BIGINT) AS intersection_area_sqm,
    ROUND(
        (ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) /
         NULLIF(ST_Area(ST_Transform(c.geom, 5070)), 0) * 100.0)::numeric, 2
    ) AS pct_of_county,
    ROUND(
        (ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) /
         NULLIF(ST_Area(ST_Transform(d.geom, 5070)), 0) * 100.0)::numeric, 2
    ) AS pct_of_cd,
    CASE
        WHEN ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) /
             NULLIF(ST_Area(ST_Transform(c.geom, 5070)), 0) >= 0.999 THEN 'CD_IN_COUNTY'
        WHEN ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) /
             NULLIF(ST_Area(ST_Transform(d.geom, 5070)), 0) >= 0.999 THEN 'COUNTY_IN_CD'
        ELSE 'SPLIT'
    END AS relationship,
    (ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) /
     NULLIF(ST_Area(ST_Transform(c.geom, 5070)), 0) > 0.5) AS is_dominant,
    NOW() AS computed_at
FROM {county_table} c
JOIN {cd_table} d
    ON c.vintage_year = d.vintage_year
    AND c.vintage_year = %s
    AND ST_Intersects(c.geom, d.geom)
    AND NOT ST_Touches(c.geom, d.geom)  -- exclude edge-only contacts
WHERE
    -- optional state filter
    (%s::text IS NULL OR c.geoid LIKE %s || '%%')
    -- minimum-overlap filter
    AND ST_Area(ST_Transform(ST_Intersection(c.geom, d.geom), 5070)) /
        NULLIF(ST_Area(ST_Transform(c.geom, 5070)), 0) >= (%s / 100.0)
ON CONFLICT (siege_county_id, siege_cd_id, year)
DO UPDATE SET
    intersection_geom = EXCLUDED.intersection_geom,
    intersection_area_sqm = EXCLUDED.intersection_area_sqm,
    pct_of_county = EXCLUDED.pct_of_county,
    pct_of_cd = EXCLUDED.pct_of_cd,
    relationship = EXCLUDED.relationship,
    is_dominant = EXCLUDED.is_dominant,
    computed_at = NOW();
```

Repeat structurally for VTD-CD (different table; `pct_of_vtd` instead of `pct_of_county`; no `relationship` field).

## Open questions for the maintainer

1. **Is the current Python `geom.area` actually computing degrees-squared instead of meters?** If yes, the percentages on existing rows are uninterpretable (degree-squared/degree-squared cancels into a ratio that's NOT proportional to ground-area-on-a-curved-earth). My proposed SQL fixes this by projecting to EPSG:5070 before measuring. Confirm this is the desired correction, not a behavior change that will break downstream consumers reading the old (wrong) percentages.

2. **`relationship='SPLIT'` threshold (currently 99.9)**: preserve as-is or revisit? The pre-existing code uses 99.9% to mean "fully contained." Reasonable but worth confirming.

3. **`is_dominant = pct_county > 50.0` definition**: preserve exact semantics? The pre-existing Python is `pct_county > 50.0`, the proposed SQL uses `> 0.5` (decimal form of the same threshold). Match the existing behavior.

4. **Production cron impact**: when does this run, and how does the maintainer want to validate the new path? Options:
   - (a) Side-by-side compare: keep the Python loop AND run the SQL on a small state (RI or DC), diff results before flipping.
   - (b) Acceptance test: load a known-shape fixture, run both, assert byte-equal results.
   - (c) Cutover with rollback: run SQL on all states; keep Python script as a `compute_geographic_intersections_legacy.py` for one cron cycle.

5. **Migration impact**: existing rows in `sw_geo_intersection_county_cd` may have post-Python-area percentages that don't match what the SQL would produce. Option:
   - (a) Truncate-and-rebuild: drop existing rows + recompute everything via SQL. Clean. Loses any rows callers may have annotated.
   - (b) Side-by-side: keep both rule sets; new SQL writes to a new table; cut over after validation.

## What this PR delivers

Just the design note. No code. Sign-off pattern:
- You approve the design (or request changes — most likely on (1), the area-units bug).
- I open a follow-up PR with the implementation + side-by-side validation harness on RI.
- Once validation matches, a third PR flips the cron over.

## Risk if rushed

The Python code's area-units bug (if real) means existing percentages are decoupled from ground reality. Shipping the SQL fix without the maintainer's eyes risks:
- New percentages diverging from old by a non-uniform factor (latitude-dependent).
- Downstream consumers (analysts running queries on these percentages) seeing the data shift without knowing why.
- The "is_dominant" boolean flipping for rows near the 50% boundary.

This is exactly the design-PR-first scenario the `think` gate exists for.
