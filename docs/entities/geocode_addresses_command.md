# geocode_addresses management command (Django command, socialwarehouse.geo)

**Definition:** `socialwarehouse/geo/management/commands/geocode_addresses.py`
**Surveyed at:** 2026-05-19 (seeded via survey-context NO-DOC path during M6 fix)
**Owner:** geo / address-loading maintainers

## Shape

Django management command that geocodes `Address` rows where `geocoded=False`. Two-phase pipeline:

1. **Phase 1 — Census batch geocoder.** Streams addresses in chunks of `batch_size` through the Census Bureau batch API. Per-chunk `bulk_update` with `ADDRESS_BULK_UPDATE_FIELDS`.
2. **Phase 2 — Nominatim fallback.** Receives the `census_unmatched` list from Phase 1 (in `dual` mode) or its own queryset (in `nominatim-only` mode). Same streaming + bulk_update shape.

## CLI flags

| Flag | Effect |
|---|---|
| `--source {dual,census-only,nominatim-only}` | Which phases to run. |
| `--batch-size N` | Chunk size for Census batch API + bulk_update flushes. |
| `--limit N` | Cap total addresses processed. |
| `--force` | Re-geocode rows where `geocoded=True`. |
| `--dry-run` | Print what would be processed; no DB writes. |
| `--nominatim-url URL` | Override Nominatim endpoint. |

## State invariants (post-M6 fix)

**`geocoded=True` implies `geom IS NOT NULL`.** Both phases enforce: the address is only marked `geocoded=True` AFTER `lat` and `lon` are non-falsy AND `geom` is populated as a `Point(lon, lat, srid=4326)`.

**Pre-M6/SW#150:** Census's `matched=True` was the gate. Census occasionally returns `matched=True` with `lat=None`/`lon=None` (street + city resolved but no coords); those rows flipped `geocoded=True` while leaving `geom=NULL`. Downstream filters on `geocoded=True` alone returned ghost rows that spatial joins silently dropped.

**Post-fix:** matched-without-coords is demoted to `census_unmatched` and Phase 2 (Nominatim) gets a real try at it.

## Bulk-update pattern (post-M1+M2+M3 fix)

- `ADDRESS_BULK_UPDATE_FIELDS` is an explicit module constant listing every field that `bulk_update` is allowed to write. Adding a new write requires adding the field to the constant in the same diff.
- `DB_BULK_CHUNK = 500` controls per-flush write size.
- `_yield_chunks(iterable, chunk_size)` is a stand-alone generator (testable in isolation).
- Phase 1's `chunk_map` is local to a single batch (no cross-phase shared state).
- Phase 2's source is either `iter(census_unmatched)` (dual mode) or `queryset.iterator()` (nominatim-only).

## Callers / consumers

- `python manage.py geocode_addresses ...` (operator-invoked)
- Cron / Celery scheduled tasks

## Cross-references

- `socialwarehouse.warehouse.fact.Address` — the model written to.
- `socialwarehouse.geo.census_geocoder.geocode_batch_chunked` — Census API client.
- `siege_utilities.geo.nominatim.use_nominatim_geocoder` — Nominatim wrapper.

## Known assumptions / gotchas

- **`geocoded=True` implies `geom IS NOT NULL`** (M6 post-fix; see above).
- **Census `matched=True` is not coordinate-bearing on its own** — the upstream API can mark a row matched without populating lat/lon. Phase 1's filter respects this.
- **Phase 2 in dual mode iterates the in-memory list** (`census_unmatched`). For very large geocoding runs (millions of rows) the memory cost grows with the Phase-1 unmatched count. Acceptable today (typical unmatched fraction is <5% of input).

## Survey log

- 2026-05-19: Seeded via survey-context NO-DOC path during M6 / SW#150 fix. Documents the post-M6 invariant and the existing post-M1/M2/M3 bulk-update + chunking shape. M4 (#148) closed as obsolete (no `address_map` exists post-refactor). M5 (#149 — PostGIS-side intersection rewrite) and M7 (#151 — export_to_delta advisory inconsistency) remain open.
