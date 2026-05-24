# How to operate the orchestration layer

Covers the day-to-day operations: running locally, debugging failed
assets, and deploying to production.

## Local development

### One-time setup

```bash
# In your SW dev venv
pip install -e ".[orchestration]"

# Confirm the optional extra installed cleanly
python -c "import dagster, dagster_postgres, dagster_spark; print('OK')"
```

Set the standard SW env vars in your `.env` (the orchestration layer
reads the same vars `delta/config.py` reads):

```env
DJANGO_SETTINGS_MODULE=socialwarehouse.settings.dev
SW_WAREHOUSE_ROOT=file:///tmp/sw-warehouse
SW_CATALOG=socialwarehouse
SW_VINTAGE=2020
```

If your local Postgres + PostGIS aren't already running, start them
via `docker-compose up postgres` (or however your dev env is wired).

### Launch the Dagster UI

```bash
dagster dev -m socialwarehouse.orchestration
```

Open http://localhost:3000. You should see:

- **Assets** tab — the asset graph (bronze → silver → gold → postgis)
- **Jobs** tab — `geo_refresh`
- **Schedules** tab — `geo_nightly_schedule` (disabled by default in `dagster dev`)
- **Sensors** tab — `bronze_addresses_arrival` (disabled by default)

`dagster dev` launches three processes: the **webserver** (UI), the
**daemon** (runs schedules + sensors), and the **gRPC code server**
(loads your code, isolated from the webserver). The daemon is what
fires schedules and sensors in the background; without it, the UI
shows definitions but nothing actually runs.

### Materialize an asset from the CLI

```bash
# A single asset:
dagster asset materialize -m socialwarehouse.orchestration \
  --select 'warehouse/silver/addresses_typed'

# The full geo graph (skip the bronze SourceAsset):
dagster asset materialize -m socialwarehouse.orchestration \
  --select 'warehouse/silver/* warehouse/gold/* postgis/geo/*'

# Everything (Dagster's wildcard):
dagster asset materialize -m socialwarehouse.orchestration --select '*'
```

The `--select` flag uses Dagster's asset-selection syntax. Common
patterns:
- `'<key>'` — exact key
- `'<key>+'` — the key and all downstream
- `'+<key>'` — the key and all upstream
- `'<group>/*'` — all assets in a group (e.g. `silver/*`)

### Run a job

```bash
dagster job execute -m socialwarehouse.orchestration -j geo_refresh
```

Jobs are useful for grouping assets that should always run together
(same retry policy, same alerting, same config).

## Debugging a failed asset

### Failure reported in the UI

When an asset fails in the Dagster UI, click into the run, then:

1. **Click the failed asset's step** in the run view — Dagster shows
   the structured logs from `context.log.info(...)` calls.
2. **Look for the stack trace** at the bottom of the step view. Most
   asset failures fall into one of these buckets:

| Error pattern | Likely cause | Fix |
|---|---|---|
| `RuntimeError: WAREHOUSE_ROOT=... requires S3 credentials` | S3 creds not set in env | Set `S3_ACCESS_KEY` + `S3_SECRET_KEY`, or point `SW_WAREHOUSE_ROOT` at a local `file://` path for dev |
| `py4j.protocol.Py4JJavaError: Failed to load Delta` | Delta extension not registered | Confirm `SparkResource.enable_sedona=True` (default) and that the Spark session was built via `delta.config.get_spark_session()` |
| `ModuleNotFoundError: No module named 'django'` | DJANGO_SETTINGS_MODULE not set when `PostGISResource` initializes | Set `DJANGO_SETTINGS_MODULE` in `.env` or Dagster code-location env config |
| `AssetCheckEvaluation: row count dropped 90%` (custom check) | Upstream data shape regression | Run the upstream asset's rule-1 measurement; check ingestion pipeline |
| `dagster._core.errors.DagsterInvariantViolationError: AssetKey ... not found` | Dep asset's key changed without updating the consumer | grep for the old key and update consumers |

### Failure not reported (asset stuck running)

If an asset doesn't fail but doesn't complete:

1. **Check Spark UI** at http://localhost:4040 (default) — is the
   query stuck in a stage? If yes, the issue is in the Spark
   execution, not Dagster.
2. **Check the asset's `context.log` output** — was the last logged
   message a `count()` call? `count()` on a large Delta table can
   take minutes to hours; consider switching to an approximate count
   or skipping the metadata count for assets that materialize huge
   tables.
3. **Check `dagster job execute --debug` output** — runs the asset
   in foreground with verbose logging.

### Sensor not firing

If `bronze_addresses_arrival` (or any sensor) isn't kicking jobs:

1. **Confirm the daemon is running.** In `dagster dev` output, look
   for "daemon running" messages. If absent, the daemon crashed —
   restart `dagster dev`.
2. **Confirm the sensor is enabled in the UI.** Sensors default to
   disabled in `dagster dev`. Toggle on in the Sensors tab.
3. **Check the sensor's cursor.** In the Sensors tab, click the
   sensor, then "Cursor" — shows the last evaluation's cursor
   value. If the cursor advanced but no run fired, the cursor
   logic may be skipping (legitimately, if no new commit). If the
   cursor didn't advance, the probe is failing — check the
   sensor's logs.
4. **Verify the probed Delta table exists.** The sensor calls
   `DESCRIBE HISTORY delta.\`<path>\``; if the path doesn't exist
   yet, the sensor skips with "probe failed". Materialize the
   bronze asset at least once before the sensor can observe it.

### Asset is correct but takes too long

1. Run `EXPLAIN` on the underlying Spark query (factor the
   transform into a function you can call from a notebook).
2. Check whether the asset is doing a `count()` for metadata — if
   the table is huge, count is expensive. Replace with `None` or
   an approximate count in the factory's `MaterializeResult`.
3. Confirm the Spark cluster has the expected resources
   (`kubectl exec <spark-pod> -- spark-shell --conf 'spark.executor.memory'`
   per `delta/config.py`'s rule-2 inventory).
4. For PostGIS materializations on large datasets, the current
   `to_sql` path won't scale — SW#280 tracks the COPY-based replacement.

## Production deployment

`dagster dev` is for local development only. Production runs three
separate processes:

### 1. The code server (loads your code)

```bash
dagster api grpc \
  --module-name socialwarehouse.orchestration \
  --host 0.0.0.0 \
  --port 4000
```

Containerize this and point Dagster's `workspace.yaml` at it. The
code server is isolated from the webserver, so SW code changes
deploy by restarting the code server without restarting the UI.

### 2. The webserver (UI)

```bash
dagster-webserver -w workspace.yaml -p 3000
```

The `workspace.yaml` lists the code server(s):

```yaml
load_from:
  - grpc_server:
      host: socialwarehouse-orchestration-code
      port: 4000
      location_name: socialwarehouse
```

### 3. The daemon (runs schedules + sensors)

```bash
dagster-daemon run -w workspace.yaml
```

The daemon needs the same `workspace.yaml` so it knows what code
servers to communicate with.

### Dagster's own storage

Dagster needs **its own Postgres database** for run storage,
schedule state, sensor cursors, and event logs. **Do NOT use SW's
domain Postgres for this in production** — Dagster's writes are
chatty and would compete with the domain workload.

`dagster.yaml` (place at `$DAGSTER_HOME`):

```yaml
storage:
  postgres:
    postgres_db:
      hostname: dagster-postgres
      port: 5432
      username: dagster
      password:
        env: DAGSTER_PG_PASSWORD
      db_name: dagster
```

For local dev, sharing SW's Postgres is fine — Dagster creates its
own tables under a `dagster_` prefix and won't collide.

### Recommended deployment shape

| Component | Container | Notes |
|---|---|---|
| Webserver | `socialwarehouse-orchestration-webserver` | Public-facing (behind auth); exposes UI on 3000 |
| Daemon | `socialwarehouse-orchestration-daemon` | One replica only (multi-daemon causes duplicate schedule fires) |
| Code server | `socialwarehouse-orchestration-code` | Multiple replicas OK; webserver load-balances |
| Run worker | spawned by daemon per run | Configured via `dagster.yaml run_launcher` — for SW, use `k8s_run_launcher` so each asset run gets a clean pod |
| Dagster Postgres | `dagster-postgres` | Separate from SW's app Postgres |

### Production monitoring

- Dagster's UI shows run history, failed runs, sensor health
- Forward Dagster's logs to your standard log aggregator (see
  SW#280 for the Dagster ↔ SW logger integration sub-issue)
- Alert on failed runs via Dagster's `RunFailureSensor` (build one
  per environment that pages on-call)
- Track schedule lateness as a key metric — a schedule that's
  hours late silently is the failure mode worth catching early

### Backfills in production

```bash
dagster asset backfill -m socialwarehouse.orchestration \
  --select '*addresses_enriched' \
  --partition-key 2010
```

Once SW#281 (partitioned-assets backfill strategy) lands, backfills
get first-class UI support. Until then, ad-hoc backfills are
explicit CLI invocations.

## See also

- [README.md](README.md) — index + asset graph diagram
- [reference.md](reference.md) — env var matrix, asset key conventions
- [how-to-add-asset-to-existing-domain.md](how-to-add-asset-to-existing-domain.md) — author workflow
- Dagster's own deployment docs: https://docs.dagster.io/deployment
