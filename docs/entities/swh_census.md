# swh/census.py (Python module, swh.census)

**Definition:** `swh/census.py`
**Surveyed at:** 2026-05-18 (seeded via survey-context NO-DOC path during S1 silent-partial-result fix)
**Owner:** swh / data-loading maintainers

## Shape

Census TIGER boundary download + PostGIS loading via `siege_utilities.census.CensusDataSource` and `siege_utilities.geo.spatial_transformations.PostGISConnector`.

Public functions (post-S1/#131 with structured returns):

| Function | Returns | Purpose |
|---|---|---|
| `download_census_boundaries(state_fips, boundary_types=None, year=None)` | `DownloadResult` | Download TIGER files for one state across requested boundary types. |
| `load_census_to_postgis(state_fips, boundary_types=None, year=None, connection_string=None, schema="public")` | `LoadResult` | Download AND load to PostGIS for one state. |
| `download_all_states(boundary_types=None, year=None)` | `dict[state_fips, DownloadResult]` | Same as `download_census_boundaries` across all configured states. |
| `load_all_states_to_postgis(boundary_types=None, year=None, ...)` | `dict[state_fips, LoadResult]` | Same as `load_census_to_postgis` across all configured states. |

## Return types (post-S1/#131)

```python
class DownloadResult(NamedTuple):
    successes: dict[str, gpd.GeoDataFrame]  # boundary_type -> GeoDataFrame
    failures: dict[str, Exception]          # boundary_type -> exception

    @property
    def any_failed(self) -> bool: ...
    @property
    def all_failed(self) -> bool: ...


class LoadResult(NamedTuple):
    successes: dict[str, str]                # boundary_type -> created table name
    failures: dict[str, Exception]           # boundary_type -> exception
                                             # (download error or upload error)

    @property
    def any_failed(self) -> bool: ...
```

Pre-fix the functions returned `dict[str, GeoDataFrame]` / `dict[str, str]`; per-boundary-type failures were logged but invisible to callers — the result dict simply lacked the failed keys, and callers had no way to distinguish "not requested" from "requested but failed." Post-fix callers must explicitly handle `.failures` or check `.any_failed`.

## CLI integration

`swh download-census` and `swh load-census` exit with code 2 if any per-boundary-type failure surfaces. Exit 0 means all-success. Exit 1 means usage error (no --state or --all-states).

## Callers / consumers

- `swh/cli.py:download_census` / `load_census` — primary callers.

## Cross-references

- `siege_utilities.census.CensusDataSource` — handles TIGER URL construction + download.
- `siege_utilities.geo.spatial_transformations.PostGISConnector` — handles PostGIS upload.
- Cross-app: **#162 / SU#516** — PostGISConnector.upload_spatial_data silently drops all tabular columns. Until SU upstream lands, `load_census_to_postgis` produces tables with geometries only; attribute fields like GEOID / NAME / vintage_year are not written. The `LoadResult.successes` map of "successful uploads" is misleading until SU#516 lands; the upload returns True but writes incomplete tables.

## Known assumptions / gotchas

- **Per-boundary-type failures are reported, not raised.** The function continues processing other boundary types even if one fails. Callers wanting fail-fast behavior must check `result.any_failed` and exit / raise themselves.
- **`upload_spatial_data` returns False on failure without raising.** Post-S1 fix: the `False` return is converted into a `RuntimeError` entry in `LoadResult.failures` so callers can distinguish exception-driven failures from boolean-false failures uniformly.
- **Cross-app data-loss bug (SW#162 / SU#516).** Tables created via `load_census_to_postgis` will have only `(id, geom)` columns until the SU fix lands. The TIGER attribute columns (GEOID, NAME, vintage_year, ALAND, AWATER, etc.) are silently dropped at the upload layer.

## Survey log

- 2026-05-18: Seeded via survey-context NO-DOC path during S1 / SW#131 fix. Pre-fix the download functions returned bare dicts with silent partial failures; post-fix they return structured `DownloadResult` / `LoadResult` NamedTuples with explicit successes + failures. CLI gained exit-code-2 on any per-boundary-type failure.
