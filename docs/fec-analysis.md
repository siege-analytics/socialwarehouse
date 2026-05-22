# FEC campaign-finance graph analysis

PySpark + GraphFrames pipeline for building and analyzing the FEC
campaign-contribution graph: committees and candidates as vertices,
contributions and official-linkage relationships as edges.

Migrated from the deleted `fec_project_feb25` branch and modernized
under SW#34 (May 2026). Pre-modernization the scripts were
side-effect-at-import; this version exposes function entry points
plus Click CLI commands.

## Prerequisites

- PySpark 4.x + GraphFrames installed (provided by `swh[spark]` extras).
- FEC bulk-data CSVs unpacked under `FEC_BASE_PATH/bulk/<cycle>/`. The
  expected files per cycle:
  - `cm**.txt`     — Committee Master
  - `cn**.txt`     — Candidate Master
  - `webl**.txt`   — Webl summary
  - `ccl**.txt`    — Candidate-Committee Linkage
  - `itpas2**.txt` — Contributions to candidates (PAS2)
  - `itoth**.txt`  — Other transactions (OTH)
- Header CSVs at `FEC_BASE_PATH/bulk/` (cycle-independent):
  `cm_header_file.csv`, `cn_header_file.csv`, etc.

Download the bulk data from https://www.fec.gov/data/browse-data/?tab=bulk-data
or via your existing FEC-ingest tooling. SW#34 leaves that fetch out of
scope; the existing scripts (`scripts/fetch.py`) cover Census + RDH +
ACS sources but not FEC bulk.

## Configuration

Environment variables (loaded from `.env`):

| Var | Default | Purpose |
|---|---|---|
| `FEC_BASE_PATH` | `/mnt/data/electinfo` | Root for FEC data |
| `FEC_BULK_SUBDIR` | `bulk` | Subdir under base for raw CSVs |
| `FEC_GRAPH_SUBDIR` | `graph` | Subdir under base for parquet output |
| `SPARK_APP_NAME` | `socialwarehouse` | Spark app name |
| `SPARK_MASTER` | `local[*]` | Spark master URL (cluster injects this) |
| `SPARK_DRIVER_MEMORY` | `2g` | Driver memory |
| `SPARK_EXECUTOR_MEMORY` | `2g` | Executor memory |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | from `swh.config.DatabaseSettings` | Target for centrality-report JDBC writes |

## Workflow

### 1. Start the Spark stack

```bash
make up-spark
```

(Or run locally if PySpark + GraphFrames + the JDBC driver are all
installed; not the typical case.)

### 2. Build the graph

```bash
python -m swh.cli fec-build-graph --cycle 2024
```

Reads `FEC_BASE_PATH/bulk/2024/*.txt`, joins them via GraphFrames,
writes two parquet datasets to `FEC_BASE_PATH/graph/`:

- `all_data_vertices.parquet`
- `all_data_edges.parquet`

For a different bulk-data location:

```bash
python -m swh.cli fec-build-graph --cycle 2024 \
  --bulk-path /data/electinfo/bulk \
  --graph-output-path /data/electinfo/graph
```

### 3. Run centrality

```bash
python -m swh.cli fec-centrality
```

Reads the graph parquet from `FEC_BASE_PATH/graph/`, computes per-party
committee-centrality aggregates, and writes them to PostgreSQL as
`committee_centrality_DEM` and `committee_centrality_REP` (default
parties). Override the party list:

```bash
python -m swh.cli fec-centrality --party DEM --party REP --party IND
```

JDBC connection info comes from `settings.database` (POSTGRES_* env vars).

### 4. Inspect the centrality tables

```sql
SELECT cmte1_name, cmte2_name, total_amount
FROM committee_centrality_DEM
ORDER BY total_amount DESC
LIMIT 25;
```

## Vertex / edge schema

### Vertices

| Label | Source | Key |
|---|---|---|
| `Committee` | `cm**.txt` | `CMTE_ID` |
| `Candidate` | `cn**.txt` | `CAND_ID` |
| `Campaign`  | `webl**.txt` | `CAND_ID` |

Vertex `id` format: `<Label>:<source-key>` (e.g. `Committee:C00000123`).

### Edges

| Label | Source | Direction |
|---|---|---|
| `OfficialLinkage` | `ccl**.txt` | Candidate → Committee |
| `Transaction`     | `itpas2**.txt` | Committee → Candidate |
| `Transaction`     | `itoth**.txt`  | Committee → entity-type-derived |
| (stub)            | synthesized from Candidate vertices | Candidate → Campaign |

The `itoth` edges use `ENTITY_TP` to derive the destination label. The
mapping is in `swh.analysis.fec.build_graph.ENTITY_TYPE_TO_LABEL`.

## Latent-bug audit fixes (SW#34 modernization)

Three pre-existing bugs were fixed during the modernization:

1. **`entity_type_to_label` was always None.** The pre-modernization
   `match` statement had no `return` or assignment in any case arm, so
   all `itoth` edges had `dst = ":<OTHER_ID>"` (no entity-label prefix).
   Now a falsifiable dict lookup with a doctest.
2. **Dead path assignment.** `DATA_EXPORTS = pathlib.Path(BASE_PATH / "graph")`
   was overwritten one line later by `DATA_EXPORTS = BULK_DATA_BASE_PATH / "exports"`.
   The intended `BASE_PATH/graph` location was dead code. Now a single
   `FEC_GRAPH_SUBDIR` setting drives both build and read paths.
3. **End-to-end was broken.** `build_graph` wrote to `bulk/exports`
   while `centrality` read from `graph/` — different directories.
   Both now use `settings.fec.graph_path`.

## Limitations

- The `EntityType → label` mapping (`ENTITY_TYPE_TO_LABEL`) covers
  CAN/CCM/COM/PAC/PTY. Other FEC ENTITY_TP codes resolve to the empty
  string (and produce edges with `dst = ":<OTHER_ID>"`). Extend the
  map as additional ENTITY_TP codes appear in upstream data.
- The JDBC write uses `mode("overwrite")` which DROPs and recreates the
  table each run. Add a `--mode` flag if append-semantics are needed.
- Cycles before 2008 may have different header-file shapes; only 2020+
  is currently tested.

## Cross-references

- Original ticket: [SW#34](https://github.com/siege-analytics/socialwarehouse/issues/34)
- Modernization audit comment: see #34's 2026-05-22 audit-findings comment
- Spark stack: `docker-compose.yml` `spark` and `full` profiles
- Settings: `swh/config.py` (`SparkSettings`, `FECSettings`, `DatabaseSettings`)
