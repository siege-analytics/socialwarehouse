# Geo ORM discipline (in-repo rule)

**Surveyed at:** 2026-05-19
**Owner:** geo + warehouse maintainers
**Companion skill:** `geodjango-server-side-math` (workspace skills tree)

## The reflex

This project uses GeoDjango against PostGIS. **Geometry math runs server-side.** Reach for `django.contrib.gis.db.models.functions.*` (`Intersection`, `Union`, `Difference`, `Area`, `Length`, `Distance`, `Transform`, `Centroid`, `Buffer`, ...) inside a `.annotate(...)` or filter expression. PostGIS does the math; only result attributes cross the wire.

The antipattern is calling `geom1.method(geom2)` on a Python `GEOSGeometry` inside a loop. Both geometries cross the wire as WKB, GEOS computes the result in Python, and any write goes back as a third serde. Same `libgeos` runs in both places — no compute advantage, only round-trip cost.

## The recognition test

Read the code as it's written. If you see any of these *inside* an iteration over a queryset (or in a per-row service callback), it's the antipattern:

- `.intersection(`, `.union(`, `.difference(`, `.symmetric_difference(` on a `.geom`
- `.area`, `.length`, `.centroid`, `.envelope` on a `.geom`
- `.distance(`, `.contains(`, `.touches(`, `.within(`, `.overlaps(`, `.crosses(`, `.disjoint(` on a `.geom`
- `.buffer(`, `.simplify(`, `.transform(` on a `.geom` inside a loop body

## The fix shape

```python
from django.contrib.gis.db.models.functions import Area, Intersection, Transform

cd_rows = (
    CongressionalDistrict.objects
    .filter(vintage_year=year, geom__intersects=county.geom)
    .annotate(
        intersection_geom=Intersection("geom", county.geom),
        intersection_area_m2=Area(
            Transform(Intersection("geom", county.geom), srid)
        ),
    )
)
```

For Area and Length, **project to a metric CRS before measuring**. `geom.area` on a 4269- or 4326-SRID geometry returns degree-squared, which is not a planar area on a curved earth. Use `Area(Transform(geom, <projected_srid>))`. The per-region projection lookup lives at `socialwarehouse/geo/projection.py`.

## The exceptions

Python-side geometry calls are **not** the antipattern when:

- **Building a value object from non-database input.** `Point(lon, lat, srid=4326)` from a user-supplied lat/lon, or a geocoder result — that point is then passed to a queryset (`Model.objects.filter(geom__contains=point)`), which runs server-side. See `socialwarehouse/api/geo/views.py` lines 170 and 345 for the canonical example.
- **One-time normalization, then many filters.** `point.clone()` + `point.transform(4269)` once per address, followed by many `Model.objects.filter(geom__contains=point, ...)` calls. See `socialwarehouse/geo/management/commands/assign_boundaries.py:272` — the alternative (wrapping every filter in `Transform(...)`) is wordier for the same SQL.
- **Single-row diagnostic.** After `qs.first()` returns one row, accessing `.geom.area` for a print or one-shot computation is fine. The antipattern is the *loop* shape, not the access pattern.

## Audit baseline (2026-05-19)

A full grep of `socialwarehouse/` for the antipattern signatures (`.intersection(`, `.union(`, `.difference(`, `.area`, `.distance(`, `.contains(` on a Python `GEOSGeometry`) found **exactly one instance**: `geo/management/commands/compute_geographic_intersections.py`. That instance is fixed by the M5 work tracked in issue #149 (design note SW#182, implementation SW#184).

The audit confirms SW is otherwise well-shaped around the ORM. This doc exists to keep it that way, not to remediate a backlog.

## Worked example

The pre-M5 `compute_geographic_intersections.py` is the canonical antipattern, preserved in git history. The post-M5 form (`Intersection`/`Area`/`Transform` annotations + per-region SRID lookup from `socialwarehouse/geo/projection.py`) is the canonical fix.

For the full design reasoning (including when to break the rule for a raw-SQL `INSERT...SELECT` form, and the three footguns that path carries), see `docs/designs/m5-postgis-st-intersection.md`.

## When to break the rule

Only when measurement says you must. The full bulk-rewrite path (raw `INSERT ... SELECT ST_Intersection ... ON CONFLICT DO UPDATE`) is a real performance win over the ORM annotation form, but it carries three footguns the annotation form does not: `_meta.db_table` introspection, SRID reconciliation, `ON CONFLICT (...)` column-vs-constraint matching. Adopt only after measuring the annotation form and judging it insufficient. The M5 design note documents this path in full.
