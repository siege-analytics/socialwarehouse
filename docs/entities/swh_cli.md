# swh.cli (CLI module)

**Definition:** `swh/cli.py`
**Surveyed at:** 2026-05-19 (seeded via survey-context NO-DOC path during S5 logging fix)
**Owner:** ops / data-loading maintainers

## Shape

Click-based CLI exposing data-loading commands. Entry: `python -m swh.cli <command>` or via Makefile targets.

| Command | Purpose |
|---|---|
| `download-census` | Fetch Census boundary shapefiles for one or more state FIPS codes. |
| `load-census` | Download + load Census boundaries into PostGIS. |
| `load-voters` | Load a voter-file CSV into PostGIS as a spatial table (delegates to `swh.voters.load_voter_file`). |
| `info` | Print resolved configuration (DB host/name/user, census year, etc.). |

## Logging configuration (post-S5 fix)

Root logging is configured inside the `cli()` group callback via `_configure_cli_logging()`, NOT at module import. Importing `swh.cli` (from tests, notebooks, downstream packages) no longer reconfigures the host process's root logger.

**Pre-S5/SW#135:** `logging.basicConfig(...)` ran at module top-level scope. Any importer of `swh.cli` inherited the format/level/handlers regardless of intent — silently displacing logging configuration the host had already set up. This was a side-effect-on-import anti-pattern.

**Post-S5:** `_configure_cli_logging()` is gated behind the group callback and fires only when click actually drives this module as a CLI.

## Callers / consumers

- `python -m swh.cli` (primary)
- `Makefile` targets that invoke the CLI directly
- Tests that import individual command callbacks for unit testing (post-S5 these no longer reconfigure logging)

## Cross-references

- `swh/voters.py` — `load-voters` delegates to `load_voter_file`.
- `swh/census.py` — `download-census` / `load-census` delegate to `download_census_boundaries` / `load_census_to_postgis`.
- `swh/config.py` — `info` reads `settings.database`, `settings.census`.

## Known assumptions / gotchas

- **Logging is configured only on CLI invocation** (post-S5). If a downstream caller imports a sub-command callback directly (e.g. for testing) and relies on `swh` logger handlers being present, they must configure logging themselves.
- **`logging.basicConfig` is a one-shot** (Python stdlib semantics): it is a no-op if any handler is already attached to the root logger. The CLI callback intentionally accepts that — if the host has already set up logging, we honor it.

## Survey log

- 2026-05-19: Seeded via survey-context NO-DOC path during S5 / SW#135 fix. Moved `logging.basicConfig(...)` out of module top-level into `_configure_cli_logging()`, called from the click group callback. Subprocess-based regression test verifies a sentinel handler on the root logger survives `import swh.cli`.
