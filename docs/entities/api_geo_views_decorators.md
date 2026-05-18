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
- `standardize_address(request)` — fragile parser; A7 finding
- `reverse_geocode(request)` — coord → address

### Helper conventions

- `_forward_geocode(address)` / `_reverse_geocode(lat, lon)` — return `(lat, lon)` / dict / None on miss; log exceptions at WARNING (A3 / SW#114 fix).
- `_get_demographics_for_boundaries(model, geoid)` — content_type + geoid lookup against DemographicSnapshot (see demographic_snapshot.md).
- `_serialize_boundary(obj)` — hasattr-chain serialization (A8 finding).
- `_standardize_address(address)` — comma-split parser (A7 finding).

## Known assumptions / gotchas

- **`method_decorator(cache_page(...), name="dispatch")` is class-based-view shape ONLY.** `name="dispatch"` references the `dispatch` method which exists on `View` subclasses, not on functions. Applying it to a function-based view silently no-ops the cache (A1 / SW#112 — fixed). Future cache decorators on these endpoints must apply `@cache_page(seconds)` directly.
- **Geocode helpers return `None` on miss AND on exception.** Per A3 / SW#114, exceptions are logged at WARNING with type + message + inputs. Callers can distinguish "no result" vs "geocoder failure" only via the log; the return value is the same. If a future API surface needs the distinction, change the helpers' contract and update this doc.
- **No authentication/permission classes** on any view (A9). All endpoints are publicly readable. Document any change.
- **`BOUNDARY_MODELS` registry** is the canonical list of supported boundary types. Adding a new boundary type requires updating the registry; the lookup-and-error-response pattern is duplicated across 4 endpoints (A6 finding).

## Callers / consumers

- `socialwarehouse/urls.py` (URL routing)
- Frontend / external clients via REST

## Survey log

- 2026-05-18: Seeded post-PR #122 (A1+A3 fixes). Documents the function-based-view shape that A1 violated. Future PRs that touch decorators or add endpoints must update this page in the same PR.
