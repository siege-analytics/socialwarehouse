# delta/config.py (Python module, socialwarehouse.delta.config)

**Definition:** `socialwarehouse/delta/config.py`
**Surveyed at:** 2026-05-18 (seeded via survey-context NO-DOC path during D4 lru_cache fix)
**Owner:** delta / warehouse-scale maintainers

## Shape

Spark + Delta Lake configuration. Two public functions:

| Function | Purpose |
|---|---|
| `get_spark_session(app_name="socialwarehouse", enable_sedona=False)` | Create or retrieve the JVM's SparkSession configured for Delta Lake (+ optional Sedona spatial extensions). Idempotent via Spark's `getOrCreate()`. |
| `get_table_path(tier, table_name)` | Build a Delta table path: `{WAREHOUSE_ROOT}/{tier}/{table_name}`. |

## Module constants (env-var-backed)

| Constant | Env var | Default | Notes |
|---|---|---|---|
| `WAREHOUSE_ROOT` | `SW_WAREHOUSE_ROOT` | `"s3a://socialwarehouse"` | Root path for tier directories. |
| `S3_ENDPOINT` | `S3_ENDPOINT` | `"http://10.10.0.10:9000"` | S3 / MinIO endpoint URL. |
| `S3_ACCESS_KEY` | `S3_ACCESS_KEY` | `""` | **Empty default — D5/#127 open** (silent misconfig). |
| `S3_SECRET_KEY` | `S3_SECRET_KEY` | `""` | **Empty default — D5/#127 open** (silent misconfig). |

## Singleton semantics (post-D4 fix)

`get_spark_session` is idempotent via Spark's own `SparkSession.builder.getOrCreate()` — the canonical singleton mechanism for a given JVM.

**Pre-D4 (removed in SW#126):** the function was decorated with `@lru_cache(maxsize=1)`. Two arguments (`app_name`, `enable_sedona`) hash into the cache key. Calling with different combinations evicted the prior cached session WITHOUT calling `.stop()`, leaking JVM-side state (SparkContext, scheduler, UI server, broadcast variables). The implicit-cache + explicit-resource-ownership combination is wrong; `getOrCreate()` alone is correct.

**Post-D4:** `@lru_cache` removed. Subsequent calls return the existing session unchanged regardless of `app_name` (standard Spark behavior — first call's `app_name` wins for the JVM lifetime). Sedona registration on an already-running session is idempotent; calling `get_spark_session(enable_sedona=True)` after a non-Sedona session has been created registers Sedona on the existing session.

## Callers / consumers

- `socialwarehouse/delta/enrichment.py` — calls `get_spark_session(enable_sedona=True)` for spatial join workflows.
- `socialwarehouse/delta/enrichment.py` — uses `get_table_path` to resolve bronze/silver/gold tier paths.
- `socialwarehouse/delta/tables.py` — uses `get_table_path` for the TABLES registry.
- Future Spark jobs in this codebase should call `get_spark_session()` rather than building their own `SparkSession.builder` chain — the Delta + S3 configuration is non-trivial and should not be duplicated.

## Cross-references

- `socialwarehouse/delta/tables.py` — TABLES registry references `get_table_path`.
- `socialwarehouse/delta/enrichment.py` — primary consumer.
- Sedona registration via `sedona.register.SedonaRegistrator` (optional import; warning logged if missing).

## Known assumptions / gotchas

- **`getOrCreate()` is the singleton mechanism.** Post-D4 fix (SW#126): `@lru_cache(maxsize=1)` was removed. Adding it back would re-introduce the eviction-without-stop leak. Don't.
- **`S3_ACCESS_KEY` / `S3_SECRET_KEY` default to empty string.** D5/#127 open. When unset, Spark gets `""` credentials and the failure surfaces as opaque AWS SDK errors mid-query rather than a clear ConfigError at startup. Fix: validate at module-load if `WAREHOUSE_ROOT` is `s3a://`.
- **First-call wins for `app_name`.** Calling `get_spark_session(app_name="X")` then `get_spark_session(app_name="Y")` returns the X-named session both times. Standard Spark behavior. Subsequent renaming requires stopping the existing session first.
- **`enable_sedona=False` followed by `enable_sedona=True` DOES register Sedona** on the existing session (since Sedona registration is idempotent at runtime). Useful for notebooks that start non-spatial and add spatial later.

## Survey log

- 2026-05-18: Seeded via survey-context NO-DOC path during D4 / SW#126 fix. `@lru_cache(maxsize=1)` decorator removed; docstring expanded to name why `getOrCreate()` is the singleton mechanism and what the lru_cache anti-pattern was. D5/#127 (empty-string S3 credential defaults) remains open.
