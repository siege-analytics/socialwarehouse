# delta/enrichment.py (Spark module, socialwarehouse.delta.enrichment)

**Definition:** `socialwarehouse/delta/enrichment.py`
**Surveyed at:** 2026-05-18 (seeded via survey-context NO-DOC path during D1+D2+D3 fix)
**Owner:** delta / warehouse-scale maintainers

## Shape

Spark + Sedona enrichment surface for warehouse-scale geographic operations. Two functions:

- `enrich_addresses_with_boundaries(spark, addresses_table, year=2020, boundaries_path=None)` — spatial enrichment of addresses with state / county / congressional-district boundary attributes via Sedona `ST_Contains`. Returns a DataFrame with the address columns plus `state_name`, `county_geoid`, `county_name`, `cd_geoid`, `cd_name`.
- `load_postgis_addresses_to_delta(spark, batch_size=100_000)` — JDBC ETL from PostGIS `sw_geo_address` table to the Delta `bronze.addresses` tier.
- `estimate_scale(row_count)` — Returns advisory `(engine, reason)` recommendation (`postgis` vs `spark`) based on a 1M-row threshold.

## Function contracts

### `enrich_addresses_with_boundaries`

**Inputs:**
- `spark` — `SparkSession` with Sedona registered (caller responsible; failure to register surfaces as `AnalysisException: Undefined function: ST_Contains`).
- `addresses_table` — either a key from `delta/tables.py:TABLES` (resolved via the registry) OR a raw Delta path. Brittle to typos — invalid registry-shaped strings fall through to raw-path interpretation (D8 finding).
- `year` — Census vintage year. Used to filter boundaries before joins. Defaults to 2020.
- `boundaries_path` — optional Delta path for boundaries. Defaults to `get_table_path("silver", "boundaries")`.

**Output:**
- DataFrame whose schema is the input addresses schema plus columns: `state_name`, `county_geoid`, `county_name`, `cd_geoid`, `cd_name`. All boundary-derived columns are nullable — addresses that don't intersect a polygon for a given summary level get NULLs (LEFT JOIN semantics, consistent across the three enrichment passes).

**Side effects:**
- Creates Spark temporary views: `addresses`, `boundaries`, `with_state`, `with_state_county`. Temp views are session-scoped; callers running multiple enrichments in the same session see the latest temp views.

### `load_postgis_addresses_to_delta`

JDBC read from `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` env vars; writes to `bronze.addresses`. Partitioned by `state_abbreviation` on overwrite.

## Constraints / known assumptions

- **Sedona-required.** Both spatial-join functions assume Sedona's `ST_*` UDFs are registered on the SparkSession. Caller must `get_spark_session(enable_sedona=True)` from `delta/config.py`.
- **Boundary intersection on edges produces row duplication.** An address that geometrically lies on the boundary between two polygons of the same summary level (rare but possible at coastline / national-boundary edges) joins to both and produces duplicate rows. Not currently de-duplicated.
- **`year` is filtered server-side via DataFrame API** (`F.col("vintage_year") == year`) — not interpolated into SQL strings (was D1 / SW#123, fixed in this entity's first survey log entry).
- **All three boundary enrichments use LEFT JOIN** — addresses without a matching boundary at a given level retain NULL for that level's columns rather than being dropped. Consistent across state / county / cd (was D6's inconsistency before D2's bundled fix).
- **Spatial joins are computed left-to-right** — `with_state` → `with_state_county` → `with_state_county_cd` (returned). Each step's temp view carries the address's `geom_point` through to the next join.

## Callers / consumers

- `socialwarehouse/geo/management/commands/export_to_delta.py` — Django mgmt command calling `load_postgis_addresses_to_delta`.
- Future warehouse-scale enrichment jobs (no current callers of `enrich_addresses_with_boundaries` outside ad-hoc Spark sessions).

## Cross-references

- Reads via `delta/tables.py:TABLES` registry (silver.boundaries path).
- Reads via `delta/config.py:get_table_path` for default paths.
- Writes to `bronze.addresses` Delta path (schema in `delta/tables.py:BRONZE_ADDRESSES`).

## Known gotchas

- **`.count()` is a Spark action.** Earlier versions of `enrich_addresses_with_boundaries` called `addresses.count()` inside a `logger.info` — forced a full plan execution just for the log message. Don't add `.count()` calls to logs in pipeline code. (D3 / SW#125, fixed.)
- **String interpolation of parameters into Spark SQL** is the wrong shape even when the parameter is int-typed — type safety is enforced at the signature level, not at the SQL boundary. Use DataFrame API filters before the SQL, or parameter binding (Spark 3.4+). (D1 / SW#123, fixed.)
- **Unused computed DataFrames are not free.** Building a Spark plan without returning the DataFrame still costs planner work; if a follow-up action (like `.count()` for a log) is then called on a sibling DataFrame, the unused plans may still get partially evaluated depending on cache state. Don't compute DataFrames you don't use. (D2 / SW#124, fixed.)

## Survey log

- 2026-05-18: Seeded via survey-context NO-DOC path during D1+D2+D3 bundled fix (PR pending). Documents the post-fix function contract; pre-fix gotchas captured in Known gotchas section above.
