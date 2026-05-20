# api/geo views decorator surface (DRF, socialwarehouse.api.geo.views)

**Definition:** `socialwarehouse/api/geo/views.py`
**Surveyed at:** 2026-05-18
**Owner:** api maintainers

## Shape — what's a function-based view vs class-based view

The file is **function-based throughout**. Every endpoint is `def name(request, ...)` decorated with `@api_view([...])` (rest_framework.decorators).

### Decorator stack convention

```python
@api_view(["GET"])           # outermost — DRF dispatch
@throttle_classes([...])     # rate limiting
@cache_page(seconds)         # Django caching, applied DIRECTLY (not via method_decorator)
def endpoint(request, ...):
    ...
```

Endpoints currently defined (verify against source on each touch):

- `geocode(request)` — forward + reverse via Census + Nominatim
- `boundary_list(request, boundary_type)` — list endpoint
- `boundary_detail(request, boundary_type, geoid)` — single boundary; **cache_page direct, NOT method_decorator** (A1 / SW#112 fix)
- `proximity(request)` — nearest-boundary search
- `intersections(request)` — overlap query
- `standardize_address(request)` — best-effort placeholder, naive comma-split US-only parser (A7 / SW#118 — documented as placeholder, not replaced)
- `reverse_geocode(request)` — coord → address

### Helper conventions

- `_resolve_boundary_model(boundary_type)` — single-type lookup against `BOUNDARY_MODELS`. Returns `(model, None)` on hit, `(None, Response)` with a 400 + `valid_types` list on miss. Used by `boundary_list`, `boundary_detail`, and `proximity` (A6 / SW#117 fix). Loop sites (`geocode`, `_get_demographics_for_boundaries`) iterate types and silently skip unknowns — they do NOT use this helper.
- `_forward_geocode(address)` / `_reverse_geocode(lat, lon)` — return `(lat, lon)` / dict / None on miss; log exceptions at WARNING (A3 / SW#114 fix).
- `_get_demographics_for_boundaries(model, geoid)` — content_type + geoid lookup against DemographicSnapshot (see demographic_snapshot.md).
- `_serialize_boundary(obj)` — hasattr-chain serialization. Post-A8/SW#119: chain is intentional and documented in the function docstring; BOUNDARY_MODELS span Census/political/timezone tables with genuinely different field sets (abbreviation: State only; district/congress fields: CongressionalDistrict only; timezone fields: TimezoneGeometry only; area_land/water: most Census). A per-model field map would be more code than the chain.
- `_standardize_address(address)` — comma-split placeholder (A7 / SW#118). Post-A10/SW#121: returns `{"components": {...}}` only — the previously-included `input` key was dead (the only caller surfaces the original address as `original`).

## Known assumptions / gotchas

- **`method_decorator(cache_page(...), name="dispatch")` is class-based-view shape ONLY.** `name="dispatch"` references the `dispatch` method which exists on `View` subclasses, not on functions. Applying it to a function-based view silently no-ops the cache (A1 / SW#112 — fixed). Future cache decorators on these endpoints must apply `@cache_page(seconds)` directly.
- **Geocode helpers return `None` on miss AND on exception.** Per A3 / SW#114, exceptions are logged at WARNING with type + message + inputs. Callers can distinguish "no result" vs "geocoder failure" only via the log; the return value is the same. If a future API surface needs the distinction, change the helpers' contract and update this doc.
- **All api views require authentication (post-A9/SW#120).** `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]` is set in `REST_FRAMEWORK` settings (`socialwarehouse/settings/base.py`). `DEFAULT_AUTHENTICATION_CLASSES` are DRF's built-in Session + Basic. Anonymous clients receive 401/403. A token-based scheme can be added later by appending to the auth-classes list and wiring `rest_framework.authtoken` (migration + INSTALLED_APPS). The api/geo views and the api/warehouse ViewSets are both covered by the global default.
- **`boundary_detail` cache TTL is 1 day** (post-A5/SW#116). Pre-fix was 7 days, which exceeded the actual boundary-update cadence enough to produce week-old stale responses after a re-load. No save-signal-driven invalidation yet; 24h is the blunt-instrument compromise.
- **`BOUNDARY_MODELS` registry** is the canonical list of supported boundary types. Adding a new boundary type requires updating the registry. Single-type lookups go through `_resolve_boundary_model` (which returns a standardized 400 with `valid_types` on miss); loop-sites iterate the registry directly and silently skip unknowns. Before A6/#117 the single-type pattern was duplicated across 3 endpoints with an inconsistency (`boundary_detail`'s 400 omitted `valid_types`); the helper standardizes the response shape.

## Callers / consumers

- `socialwarehouse/urls.py` (URL routing)
- Frontend / external clients via REST

## Survey log

- 2026-05-18: Seeded post-PR #122 (A1+A3 fixes). Documents the function-based-view shape that A1 violated. Future PRs that touch decorators or add endpoints must update this page in the same PR.
- 2026-05-18: A6/#117 fix — `_resolve_boundary_model` helper extracted; `boundary_detail` 400 response now includes `valid_types` (was inconsistent). Helper-conventions and BOUNDARY_MODELS notes updated.
- 2026-05-19: api/geo bundle A4+A5+A7+A8+A10 fixes (PRs SW#115, #116, #118, #119, #121). Module docstring corrected (no `BoundaryManager` wrapper exists — A4). `boundary_detail` cache_page TTL reduced 7d → 1d (A5). `_standardize_address` flagged in-source as a US-only naive placeholder; `standardize_address` view docstring marks it best-effort (A7). `_serialize_boundary` hasattr chain kept and explained inline; BOUNDARY_MODELS field-heterogeneity documented (A8). Dead `input` key dropped from `_standardize_address` return (A10).
- 2026-05-19: A9 / SW#120 fix — all api views now require authentication. `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` set globally in REST_FRAMEWORK; `DEFAULT_AUTHENTICATION_CLASSES` uses DRF's Session + Basic defaults. Anonymous clients get 401/403. Existing endpoint tests in `tests/unit/api/test_geo_api.py` updated to `force_authenticate` via a shared `_authenticate(client)` helper; new `TestGeoAPIAuthenticationRequired` class adds anonymous-denial regression tests. Token auth left as a follow-up if a non-session client is needed.
