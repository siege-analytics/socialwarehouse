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

Stop pulling geometries to Python for the intersection compute. The existing loop uses `county.geom.intersection(cd.geom)` which means: read both geoms from PostGIS as WKB → deserialize in Python → GEOS computes intersection → serialize back to WKB → write. Three serde cycles per pair plus per-pair Python orchestration. Same GEOS library that PostGIS uses; no compute advantage; only round-trip cost.

## Three options, not two (revised after operator pushback)

The original draft of this design jumped from option 0 (status quo) straight to option B (raw SQL). It missed the middle ground that GeoDjango actually provides.

| Option | What | Speed (estimated) | Risk |
|---|---|---|---|
| **0** (status quo) | `county.geom.intersection(cd.geom)` in Python. Per-pair WKB round-trip. Per-row `update_or_create`. | Slowest baseline. | Zero (current). |
| **A** (recommended starting point) | GeoDjango ORM: `qs.annotate(intersection=Intersection('geom', cd.geom), intersection_area=Area(Transform('intersection', 5070)))`. Geometry math is pushed to PostGIS via `django.contrib.gis.db.models.functions`. Per-county queryset still; only the result attributes come back to Python. | Probably 5–20× faster than option 0. No serde of geoms across the wire. | **Low.** Stays inside Django ORM. No `_meta.db_table` introspection. No raw-SQL `ON CONFLICT` constraint matching. Still uses `update_or_create` per row. |
| **B** (full bulk rewrite) | Raw `INSERT ... SELECT ... ST_Intersection ... ON CONFLICT DO UPDATE`. One query per intersection type. | Probably another 5–10× over option A. Eliminates per-county Python iteration + per-row UPSERT. | **High.** The three footguns named below (db_table introspection, SRID, ON CONFLICT-by-columns) all live here. Adopt only if measurement shows option A isn't fast enough. |

**Recommended path:** ship option A first as a focused PR. Measure the cron's apply-time. If A meets the perf bar, stop. If not, then design + ship option B with the three-footgun work already accounted for in the SQL shape below.

The shift from the original design's "B from the jump" to "A first, measure, then maybe B" is itself the right shape: don't take on the raw-SQL footguns until measurement says option A isn't enough.

## Proposed Option A shape (recommended starting point)

```python
from django.contrib.gis.db.models.functions import Intersection, Area, Transform
from django.db.models import F

# Outer loop: per county (still per-row from Python's view, but each
# iteration's geometry math is now server-side).
for county in counties.iterator():
    cd_rows = (
        CongressionalDistrict.objects
        .filter(vintage_year=year, geom__intersects=county.geom)
        .annotate(
            intersection_geom=Intersection('geom', county.geom),
            # Area in projected CRS (EPSG:5070 for CONUS) — meters^2,
            # not degree-squared. Answers M5-Q1 below.
            intersection_area_m2=Area(Transform('intersection_geom', 5070)),
            county_area_m2=Area(Transform(F('geom') if False else county.geom_transformed, 5070)),  # see note
            cd_area_m2=Area(Transform('geom', 5070)),
        )
    )

    for cd in cd_rows:
        if cd.intersection_geom.empty:
            continue
        pct_county = (cd.intersection_area_m2.sq_m / cd.county_area_m2.sq_m) * 100
        pct_cd = (cd.intersection_area_m2.sq_m / cd.cd_area_m2.sq_m) * 100
        ...
        CountyCongressionalDistrictIntersection.objects.update_or_create(
            siege_county=county, siege_cd=cd, year=year,
            defaults={
                "intersection_geom": cd.intersection_geom,  # already a GEOSGeometry
                "intersection_area_sqm": int(cd.intersection_area_m2.sq_m),
                "pct_of_county": round(pct_county, 2),
                "pct_of_cd": round(pct_cd, 2),
                ...
            },
        )
```

(Note: the `county_area_m2` annotation may need to be precomputed once per county outside the inner queryset to avoid recomputing on every CD row — engineering detail to settle at implementation time.)

What option A pushes server-side:
- `ST_Intersection(county.geom, cd.geom)`
- `ST_Area(ST_Transform(intersection, 5070))`
- `ST_Area(ST_Transform(county.geom, 5070))`
- `ST_Area(ST_Transform(cd.geom, 5070))`

What option A leaves in Python:
- The per-county loop (one query per county; not a single bulk insert).
- The per-row `update_or_create`.
- The relationship-classification logic (`SPLIT`/`COUNTY_IN_CD`/`CD_IN_COUNTY`).

That's enough Python that option B's bulk-INSERT would be faster — but option A doesn't need any of B's three footguns to ship.

## Three real footguns (apply to option B only; option A doesn't have them)

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

## Open questions for the maintainer (apply to both option A and option B)

1. **Is the current Python `geom.area` actually computing degrees-squared instead of meters?** If yes, the percentages on existing rows are uninterpretable (degree-squared/degree-squared cancels into a ratio that's NOT proportional to ground-area-on-a-curved-earth — the distortion is latitude-dependent). Both option A and option B propose `Area(Transform(geom, 5070))` which fixes this. Confirm this is the desired correction, not a behavior change that will break downstream consumers reading the old (wrong) percentages. **This is the question that gates the option A implementation PR** — answering yes means option A is a data correction + perf fix; answering no (preserve existing degree-squared semantics) means option A must NOT apply Transform and just calls Area on the unprojected geom.

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

1. **Answer Q1** (the area-units question). This gates everything below.
2. **Approve option A as the starting point** (or request a different option).
3. I open a follow-up PR with **option A** implementation + side-by-side validation harness on a small state.
4. If measurement says option A meets the perf bar, stop. Option B and its three footguns stay deferred.
5. If measurement says option A isn't fast enough, third PR ships option B per the SQL shape below.

## Entity-level lesson

This file is a small documentation surface, but the bigger lesson is one to note in the entity doc page that lives next to `compute_geographic_intersections.py`:

> When the project uses GeoDjango against PostGIS, the default reflex for any geometry computation is `django.contrib.gis.db.models.functions.*` (`Intersection`, `Area`, `Distance`, `Transform`, etc.) so the math stays server-side. Calling `geom1.intersection(geom2)` from Python serializes both geometries across the wire, defeats the database, and is no faster than the server-side version (same GEOS library, just with extra round-trips). The existing M5 code did this; the lesson is that no one measured.

## Risk if rushed

The Python code's area-units bug (if real) means existing percentages are decoupled from ground reality. Shipping ANY fix (option A or B) without the maintainer's eyes risks:
- New percentages diverging from old by a non-uniform factor (latitude-dependent).
- Downstream consumers (analysts running queries on these percentages) seeing the data shift without knowing why.
- The "is_dominant" boolean flipping for rows near the 50% boundary.

This is the design-PR-first scenario the `think` gate exists for. The Option-A-first sequencing reduces the engineering risk of the rewrite, but the data-correction question is the same either way.

## Revision history

- v1 (initial): proposed option B (raw SQL INSERT...SELECT) directly. Missed the middle ground.
- v2 (after operator pushback "If we are dealing with GeoDjango with its massive ORM, why are we manually computing intersections?"): added option A (GeoDjango ORM annotations) as the recommended starting point. Option B reserved for "if A isn't fast enough." Footguns reframed as option-B-specific. Q1 (area-units) elevated as the gating decision before any implementation begins.
