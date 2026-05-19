# swh/voters.py (Python module, swh.voters)

**Definition:** `swh/voters.py`
**Surveyed at:** 2026-05-18 (seeded via survey-context NO-DOC path during S3 lock fix)
**Owner:** swh / data-loading maintainers

## Shape

Voter-file CSV loader. Reads chunked pandas, builds Point geometries from lon/lat columns, uploads to PostGIS via `siege_utilities.geo.spatial_transformations.PostGISConnector`.

Public functions:

| Function | Purpose |
|---|---|
| `load_voter_file(filepath, table_name, ...)` | Stream-load a voter CSV into a PostGIS table. Stages first, atomic-swaps on completion. |
| `voter_file_to_geodataframe(filepath, ...)` | Read into an in-memory GeoDataFrame for Tier-3 (GeoPandas-only) processing. |
| `_coerce_and_build_geometry(df, ...)` | Internal helper. Coerces lon/lat to numeric, drops invalid rows, builds GeoDataFrame. |

## DEFAULT_COLUMNS

TargetSmart voter file convention:

| Logical | CSV column |
|---|---|
| longitude | `vb_tsmart_longitude` |
| latitude | `vb_tsmart_latitude` |
| precinct | `vb_vf_national_precinct_code` |
| county | `vb_tsmart_county_name` |
| cd | `vb_vf_cd` |
| sd | `vb_vf_sd` |
| hd | `vb_vf_hd` |

Override per-call via the `longitude_col` / `latitude_col` parameters or via CLI flags from `swh/cli.py`.

## Staging-table + atomic-swap pattern (post-S3 fix)

1. Generate uniquely-named staging table: `_staging_{table_name}_{uuid8}`.
2. For each chunk: build GeoDataFrame, upload via `connector.upload_spatial_data(gdf, staging_table, ..., if_exists="replace" on first chunk / "append" thereafter)`.
3. On all-chunks-success, run the swap inside one transaction:
   - `inspect(connector.engine).has_table(table_name, schema=schema)` — pre-check existence.
   - If target exists: `LOCK TABLE <schema>.<table_name> IN ACCESS EXCLUSIVE MODE` (post-S3/#133 fix — explicit lock acquisition before DDL).
   - `DROP TABLE IF EXISTS <schema>.<table_name>`.
   - `ALTER TABLE <schema>.<staging_table> RENAME TO <table_name>`.
4. On any chunk failure: drop the staging table; raise.

## Callers / consumers

- `swh/cli.py:load_voters` — Click command `swh load-voters <filepath> --table <name> [...]`.

## Cross-references

- `siege_utilities.geo.spatial_transformations.PostGISConnector` — handles the actual upload + engine.
- `swh/config.py:settings.database.connection_string` — default connection target.

## Known assumptions / gotchas

- **`LOCK TABLE` requires the table to exist.** Post-fix: an `inspect.has_table` pre-check guards against `relation does not exist` on first-ever loads. Without this check, naive `LOCK TABLE` would fail on the first run.
- **CSV encoding / quoting / dtype defaults.** Post-S2/#132 fix: both public read paths accept `encoding` (default `utf-8-sig` for BOM-tolerance), `dtype` (default None — pass `TARGETSMART_DEFAULT_DTYPES` for TargetSmart files), `quoting` (default `csv.QUOTE_MINIMAL`), `quotechar` (default `"`). The `TARGETSMART_DEFAULT_DTYPES` module constant preserves leading zeros on `vb_vf_national_precinct_code`, `vb_vf_cd`, `vb_vf_sd`, `vb_vf_hd`, `vb_tsmart_county_name`, `vb_tsmart_county_code`, `vb_tsmart_zip`, `zip5`, `zip9`, `county_fips`. CLI `swh load-voters` exposes `--encoding` + `--targetsmart-dtypes/--no-targetsmart-dtypes` (default on). Non-TargetSmart files: pass a custom dtype dict programmatically (the CLI does not yet accept arbitrary dtype dicts).
- **Chunk-append assumes chunk-1's column shape.** S4 / SW#134 (open): `if_exists="replace"` on chunk 1 then `"append"` on chunk 2+; if chunk 2 has different columns from chunk 1 (schema drift mid-file, late-added columns, etc.), the append silently misaligns. Verify `upload_spatial_data`'s `if_exists="append"` semantics.
- **`{schema}.{table_name}` interpolated into raw SQL — now validated and quoted.** Post-S6/SW#136 fix: `_validate_identifier` (regex `^[A-Za-z_][A-Za-z0-9_]*$`) runs against `schema`, `table_name`, and the generated `staging_table` BEFORE any I/O. Validation failure raises `ValueError` immediately; valid identifiers are double-quoted (`"foo"`) when interpolated into the LOCK / DROP / ALTER TABLE statements. Identifiers with spaces, dots, hyphens, quotes, semicolons, or leading digits are rejected. Pre-fix any value passed through `--schema` or `--table` was interpolated raw — operator-trust boundary, but a `--schema 'public;DROP TABLE x;--'` would execute.
- **Cleanup-exception warning lacks remediation hint.** S8 / SW#138 (open NIT): if staging-table cleanup fails after a load failure, the warning names the table but not how to clean it up manually.

## Survey log

- 2026-05-18: Seeded via survey-context NO-DOC path during S3 / SW#133 fix. Pattern documented covers post-S3 shape; S2 / S4 / S6 / S8 listed as open gotchas to fix in subsequent PRs.
- 2026-05-18: S2 / SW#132 fix — added `encoding`, `dtype`, `quoting`, `quotechar` parameters to both public read paths; added `TARGETSMART_DEFAULT_DTYPES` and `DEFAULT_CSV_ENCODING` module constants; CLI gained `--encoding` and `--targetsmart-dtypes/--no-targetsmart-dtypes` flags. Pre-fix `pd.read_csv` with no kwargs silently corrupted leading-zero ID columns. S4 / S6 / S8 remain open.
- 2026-05-19: S6 / SW#136 fix — added `_validate_identifier` helper, applied to `schema`, `table_name`, and `staging_table` before any I/O. Identifiers are rejected if they don't match `^[A-Za-z_][A-Za-z0-9_]*$` (bare ASCII), then double-quoted when interpolated into LOCK / DROP / ALTER TABLE DDL. Closes the injection vector on the `--schema` / `--table` CLI options. S4 / S8 remain open (S4 paused pending SU#517 merge).
