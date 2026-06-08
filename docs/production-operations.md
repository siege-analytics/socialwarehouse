# Production Operations Guide

This guide covers the operational decisions adopters need to make when their SocialWarehouse deployment outgrows the single-node defaults. It is a **decision framework**, not a prescription — each adopter's scale, hardware, compliance posture, and cloud provider will differ.

The guide assumes familiarity with [`docs/architecture.md`](architecture.md) (the three-tier warehouse pattern) and [`docs/quickstart.md`](quickstart.md) (the single-node dev setup).

Each section follows the same structure:

- **Decision** — what you're deciding
- **Triggers** — signals that you need to make this decision now
- **Options** — approaches with trade-offs
- **Default-safe recommendation** — what to do if you're unsure
- **Implementation pointer** — where the work lives (your infra repo, not here)

---

## 1. High-Availability Topology

**Decision:** Should the PostGIS tier run as a single pod, or as a primary + standby cluster?

**Triggers:**
- Unplanned downtime costs more than the operational overhead of a replica
- Database size exceeds what you can restore from backup within your RTO (recovery time objective)
- Multiple services (Django, Spark materializations, Dagster sensors) contend for the same primary

**Options:**

| Approach | Pros | Cons |
|----------|------|------|
| Single pod | Simple, no replication lag, easy to reason about | Single point of failure; restore-from-backup is your only recovery path |
| CloudNativePG (CNPG) | Kubernetes-native, ArgoCD-friendly, automated failover, WAL archiving built in | Learning curve if you haven't operated CRDs; CNPG-specific debugging |
| Patroni + etcd | Battle-tested, cloud-agnostic, rich ecosystem | More moving parts (etcd/consul cluster); manual ArgoCD integration |
| Managed service (RDS/CloudSQL) | Zero operational burden for HA | Vendor lock-in; less control over PostGIS extensions and versions |

**Default-safe recommendation:** Start with a single pod until your data volume or uptime requirements force the conversation. When you're ready, CNPG primary + 1 standby + WAL archiving to object storage is the lowest-friction Kubernetes path. If you're not on Kubernetes, a managed PostgreSQL service with PostGIS support is the pragmatic choice.

**Implementation:** SW ships CNPG (CloudNativePG) manifests in `k8s/cnpg/` as the recommended Kubernetes path:

- `cluster.yaml`: 3-instance Cluster (1 primary + 2 standbys) with PostGIS 16-3.4
- `backup-schedule.yaml`: daily base backups at 02:00 UTC, 14-day retention
- `minio.yaml`: MinIO for dev/test WAL archiving (replace with real S3/GCS in production)

See `k8s/cnpg/README.md` for prerequisites, quick-start, and production customization. The `docker-compose.yml` single-node setup remains the dev convenience; CNPG is the production path for Kubernetes adopters. Non-Kubernetes adopters should use Patroni or a managed PostgreSQL service.

---

## 2. Backup and Point-in-Time Recovery (PITR)

**Decision:** Where do WAL archives go, how often do you take base backups, how long do you retain them, and can you actually restore?

**Triggers:**
- You have data you can't re-derive from source (geocoding results, vendor-ingested records, user-contributed data)
- Database size exceeds what you can casually recreate by re-running ingest pipelines
- Compliance requires auditable backup history

**Options:**

| Component | Choices |
|-----------|---------|
| WAL archive target | S3/GCS/Azure Blob (most common); local NFS (small deployments); pgBackRest repository |
| Base backup tool | `pg_basebackup` (simple), pgBackRest (incremental + parallel), Barman (feature-rich) |
| Retention policy | Time-based (e.g., 30 days), count-based (e.g., last 7 base backups), or both |
| Restore testing | Automated periodic restore to a scratch instance (gold standard) vs. manual quarterly drills |

**Default-safe recommendation:** WAL archiving to S3-compatible storage + daily base backups via pgBackRest + 14-day retention. Test a restore before you need one — an untested backup is not a backup.

**Implementation:** If using CNPG (see §1), backup is declarative:

- WAL archiving: configured in `k8s/cnpg/cluster.yaml` under `spec.backup.barmanObjectStore`
- Scheduled base backups: `k8s/cnpg/backup-schedule.yaml` (daily at 02:00 UTC, 14-day retention)
- PITR: create a recovery Cluster CRD pointing to the WAL archive with a `recoveryTarget.targetTime` (see `k8s/cnpg/README.md` for a full example)

If managing PostgreSQL directly (non-CNPG), pgBackRest config lives alongside your PostgreSQL configuration in your infrastructure repo.

---

## 3. Connection Pooling

**Decision:** Do you need a connection pooler between your application tier and PostgreSQL, and if so, what pool mode?

**Triggers:**
- Connection count from Django workers + Celery workers + Spark executors + Dagster ops exceeds `max_connections` (default 100)
- Short-lived connections (Django request cycle) create connection churn visible in `pg_stat_activity`
- You're running multiple replicas of the Django web tier

**Options:**

| Pooler | Mode | Fits |
|--------|------|------|
| PgBouncer (transaction mode) | Releases server connection at transaction boundary | Django + DRF (short transactions, no prepared statements by default) |
| PgBouncer (session mode) | Holds server connection for client session lifetime | Spark JDBC (long-lived connections, may use prepared statements) |
| pgpool-II | Connection pooling + load balancing + replication | Overkill for most SW deployments; useful if you need query-level read/write splitting |
| Application-side pooling (SQLAlchemy pool, Django CONN_MAX_AGE) | No external component | Sufficient for small deployments; doesn't help with cross-service connection sharing |

**Default-safe recommendation:** PgBouncer in transaction mode for Django/Celery traffic. Spark and Dagster typically open fewer, longer-lived connections — route them directly to PostgreSQL (or through a separate PgBouncer instance in session mode) to avoid prepared-statement conflicts.

**Implementation:** SW ships a PgBouncer service in `docker-compose.yml` (transaction mode, enabled by default). Applications connect via `POSTGRES_HOST=pgbouncer` + `POSTGRES_PORT=6432`. Direct PostgreSQL access is preserved via `POSTGRES_DIRECT_HOST`/`POSTGRES_DIRECT_PORT` for COPY operations and migrations. Configuration lives in `docker/pgbouncer/pgbouncer.ini`.

Key PgBouncer settings (tune for your deployment):

| Parameter | Default | Production guidance |
|---|---|---|
| `default_pool_size` | 25 | Set to `max_connections / expected_distinct_users` |
| `max_client_conn` | 400 | Sum of all Django workers + Celery workers + Dagster ops + headroom |
| `min_pool_size` | 5 | Avoids cold-start latency for bursty workloads |
| `reserve_pool_size` | 5 | Emergency overflow; fires after `reserve_pool_timeout` seconds |

**PostgreSQL memory tuning profiles:**

| Parameter | Dev (4 GB) | Staging (16 GB) | Production (128 GB+) |
|---|---|---|---|
| `shared_buffers` | 1 GB | 4 GB | 32 GB |
| `effective_cache_size` | 3 GB | 12 GB | 96 GB |
| `work_mem` | 16 MB | 64 MB | 256 MB |
| `maintenance_work_mem` | 256 MB | 1 GB | 4 GB |
| `wal_buffers` | 16 MB | 64 MB | 256 MB |
| `max_connections` | 100 | 200 | 300 |
| `max_wal_size` | 2 GB | 8 GB | 16 GB |
| `checkpoint_completion_target` | 0.9 | 0.9 | 0.9 |
| `random_page_cost` | 1.1 | 1.1 | 1.1 |
| `effective_io_concurrency` | 200 | 200 | 200 |

To apply: mount a custom `postgresql.conf` via Docker volume or pass parameters via the `postgis` service's `command:` list. The Docker Compose `postgis` service already demonstrates this pattern with `pg_hba.conf`.

---

## 4. Partitioning Strategy

**Decision:** When and how to partition large fact tables and transaction tables in the PostGIS star schema.

**Triggers:**
- A single table exceeds ~100M rows or ~50 GB (query planning overhead becomes measurable)
- Sequential scans on fact tables dominate query time despite indexes
- Bulk loads (Spark→PostGIS materialization) contend with read queries on the same table
- You need to drop or archive old data without `DELETE` + `VACUUM` overhead

**Options:**

| Strategy | Partition key | Fits |
|----------|---------------|------|
| Range by time dimension | `vintage_year`, `effective_year`, `created_at` | Good default for most fact tables; aligns with how data arrives and ages |
| Range by domain-specific key | A domain FK that represents natural lifecycle boundaries | Good when your domain has a clear lifecycle concept (e.g., legislative sessions, fiscal years) |
| List by jurisdiction | `state_fips` or equivalent | Good for multi-state deployments where queries are almost always state-scoped |
| Composite (range + list) | Two-level: jurisdiction × time | Maximum partition pruning; operational complexity of managing the partition matrix |

**Default-safe recommendation:** Start without partitioning — PostgreSQL handles large tables well with proper indexes. When a specific table hits the triggers above, partition by the dimension that most closely matches your query patterns (usually time-based). Add jurisdiction sub-partitioning only if your queries are consistently state-scoped and the partition count stays manageable (rule of thumb: under 500 partitions per table).

**Implementation:** SW ships migration `0006_partition_fact_tables` which partitions three high-volume tables:

| Table | Partition Key | Range |
|---|---|---|
| `sw_fact_redistricting_plan` | `cycle_id` | Per redistricting cycle (10-year) |
| `sw_fact_vote_history` | `election_date` | Per calendar year (2016-2026) |
| `sw_fact_person_score` | `scored_at` | Per calendar year (2020-2027) |

Each table gets a `DEFAULT` partition as a safety net. Future partitions can be created manually or via pg_partman.

**pg_partman setup (production):**

```sql
CREATE EXTENSION pg_partman;

SELECT partman.create_parent(
    p_parent_table := 'public.sw_fact_vote_history',
    p_control := 'election_date',
    p_type := 'range',
    p_interval := '1 year',
    p_premake := 2
);
```

This auto-creates partitions 2 years ahead. Run `partman.run_maintenance()` on a schedule (daily cron or Dagster sensor) to create forward partitions and optionally detach old ones.

**Adding partitions manually (without pg_partman):**

```sql
CREATE TABLE sw_fact_vote_history_2027
    PARTITION OF sw_fact_vote_history
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
```

**Non-FEC adopters:** The cycle concept is domain-specific. Electoral warehouses use redistricting cycles; fiscal warehouses might use fiscal years; environmental warehouses might use monitoring periods. The partition key should match your domain's natural lifecycle boundary. Update the migration's partition ranges to match your domain.

**Not yet partitioned:** FactACSEstimate, FactDecennialCount, FactUrbanicity, FactElectionResult, FactPrecinctResult. These can be partitioned when they hit the triggers above — follow the same `RunSQL` migration pattern.

---

## 5. Cold-Tier and Columnar Storage

**Decision:** What happens to historical data that's rarely queried but must remain accessible?

**Triggers:**
- Historical partitions consume significant storage but see <1% of queries
- Storage costs on fast SSDs become meaningful relative to the value of instant access to old data
- You need to retain data for compliance but queries against it are rare and can tolerate latency

**Options:**

| Approach | Latency | Storage cost | Complexity |
|----------|---------|--------------|------------|
| Keep everything on the primary (do nothing) | Instant | Full SSD cost | None |
| Columnar extension (hydra_columnar, Citus columnar) | Sub-second (still in PostgreSQL) | 3-10× compression | Medium — need to manage columnar access methods per table |
| Detach partition + move to cheaper storage class | Seconds (re-attach on demand) | Reduced (HDD/object store) | Medium — operational runbook for detach/attach |
| Archive to Delta Lake on object storage | Minutes (query via Spark) | Lowest (S3/GCS lifecycle policies) | Low — data is already in Delta format in the warehouse's bronze/silver tiers |

**Default-safe recommendation:** The simplest path for SW adopters: historical data that's past your active query window already exists in Delta Lake (tier 1 of the warehouse). Stop materializing it to PostGIS. PostGIS holds the hot window; Delta holds everything. When you need historical data, query it via Spark. No columnar extensions, no partition gymnastics — just stop pushing old data into the serving tier.

**Implementation:** SW ships a three-tier model for partitioned fact tables:

| Tier | Tablespace | Indexes | Partitions |
|---|---|---|---|
| Hot | `pg_default` (NVMe) | Full indexes | Current + previous cycle/year |
| Warm | `warm_ts` (SSD) | Reduced (non-essential dropped) | N-2 through N-5 |
| Cold | `cold_ts` (HDD/columnar) | Minimal (PK only) | Older than N-5 |

**Tablespace setup (host-specific — run once per deployment):**

```sql
-- Create tablespaces pointing to your storage mount points
CREATE TABLESPACE warm_ts LOCATION '/mnt/ssd/pg_warm';
CREATE TABLESPACE cold_ts LOCATION '/mnt/hdd/pg_cold';
```

**Tier assessment and advancement:**

- `swh tier-status` shows current partition placement vs recommended tier
- `swh tier-status --json` for machine-readable output
- The `tier_advancement_monitor` Dagster sensor runs daily and logs recommendations for misplaced partitions

**Moving a partition to a different tier:**

```sql
ALTER TABLE sw_fact_vote_history_2018 SET TABLESPACE warm_ts;
```

**Index reduction for warm partitions:**

```sql
-- Drop non-essential indexes on warm/cold partitions
-- Keep only primary key and unique constraints
DROP INDEX CONCURRENTLY idx_vote_history_2018_person_date;
```

**hydra_columnar for cold tier (optional):**

```sql
CREATE EXTENSION IF NOT EXISTS columnar;

-- Convert a cold partition to columnar storage
SELECT columnar.alter_table_set_access_method('sw_fact_vote_history_2016', 'columnar');
```

Install hydra_columnar when your warehouse exceeds 5 TB or 5 redistricting cycles. Below that threshold, the three-tier tablespace model is sufficient.

**Decision trigger:** if warehouse > 5 TB or > 5 cycles, install columnar. Below that, the simplest approach remains "stop materializing old data to PostGIS" and query historical data via Delta Lake/Spark.

---

## 6. Hub-to-Downstream Distribution

**Decision:** How do downstream consumers (web app, analytical databases, search indexes, graph databases) get data from the PostGIS warehouse hub without querying the primary directly?

**Triggers:**
- Read traffic from the web app competes with Spark materialization writes
- You're adding consumers (OpenSearch for full-text, Neo4j for graph queries, BI tools) that shouldn't touch the primary
- You need per-consumer data subsets (e.g., one engagement gets one state's data)

**Options:**

| Pattern | Freshness | Complexity | Fits |
|---------|-----------|------------|------|
| Read replica (streaming replication) | Near-real-time | Low | Django reads; point `DATABASES['readonly']` at the replica |
| Logical replication / filtered publications | Near-real-time, subset-able | Medium | Per-consumer slices; e.g., publish only `sw_geo` tables to the web-app DB |
| `pg_dump` by partition / table | Batch (scheduled) | Low | Per-engagement analytical snapshots; cold handoffs |
| Debezium CDC → Kafka → consumers | Real-time, event-driven | High | When you need event-driven downstream updates (search index, graph sync) |
| Direct Delta Lake reads | Batch (already available) | None | Consumers that can read Parquet/Delta directly (BI tools, notebooks, Spark jobs) |

**Default-safe recommendation:** Start with a streaming read replica for Django and API traffic (`DATABASES['readonly']`). For non-PostgreSQL consumers (search, graph, BI), read from Delta Lake directly — the data is already there in a format optimized for analytical access. Logical replication and CDC are powerful but operationally expensive; defer until you have a concrete freshness requirement that batch can't meet.

**Implementation pointer:** Read replica setup is part of your HA topology (see §1). Django database routing is a settings change (`DATABASE_ROUTERS`). Delta Lake access is already built into SW's architecture.

---

## 7. Metadata Store Isolation

**Decision:** Should catalog/metadata infrastructure (Unity Catalog, Hive Metastore, or equivalent) share the same PostgreSQL instance as the warehouse data?

**Triggers:**
- You're running a Spark-based catalog (Unity Catalog, Hive Metastore) that uses PostgreSQL as its backing store
- A bad migration or schema corruption in one system could affect the other
- You want independent backup/restore and lifecycle management for metadata vs. data

**Options:**

| Approach | Pros | Cons |
|----------|------|------|
| Shared PostgreSQL instance, separate databases | Simple; one PostgreSQL to manage | Coupled blast radius; backup/restore is all-or-nothing at the instance level |
| Separate PostgreSQL instances | Independent lifecycle, backup, scaling | Two PostgreSQL deployments to operate |
| Managed metadata service (e.g., AWS Glue, Databricks-hosted UC) | Zero operational burden for metadata | Vendor coupling; may limit Spark/Sedona version choices |

**Default-safe recommendation:** Start with separate databases on the same PostgreSQL instance (low overhead). If you find that metadata operations (catalog queries, schema evolution) interfere with warehouse queries, or if you need independent backup/restore schedules, split to a separate PostgreSQL instance. The cost of splitting later is low — metadata stores are small and easy to `pg_dump`/`pg_restore`.

**Implementation pointer:** Catalog configuration lives in your Spark/Sedona configuration (`spark.sql.catalog.*` properties) and your infrastructure provisioning. SW's `docker-compose.yml` runs a single PostGIS instance for dev convenience; production topology is the adopter's decision.

---

## 8. Scheduling and Node Placement

**Decision:** What kind of compute node should the PostgreSQL pod run on, and how do you prevent it from competing with Spark/Dagster workloads for resources?

**Triggers:**
- Spark executors or Dagster ops consume memory/CPU on the same node as PostgreSQL
- WAL write latency spikes during Spark job execution
- You're running on Kubernetes and need to declare resource requests/limits

**Options:**

| Concern | Recommendation |
|---------|----------------|
| Node type | PostgreSQL benefits from fast local storage (NVMe SSDs) and consistent memory. Don't co-locate with Spark workers, which are CPU/memory-hungry and bursty. |
| Storage class | Use a storage class backed by local SSDs or provisioned IOPS (e.g., `gp3` on AWS, `pd-ssd` on GCP). Network-attached storage (EBS `gp2`, standard PDs) adds latency to WAL writes. |
| Node affinity | Label dedicated database nodes (e.g., `role=database`) and use `nodeAffinity` to pin PostgreSQL pods. Use taints to prevent Spark/Dagster from scheduling on database nodes. |
| Resource requests | Request enough memory for `shared_buffers` + `work_mem` × expected parallel queries + OS cache. PostgreSQL is memory-hungry but predictable; size generously and don't overcommit. |

**Default-safe recommendation:** Dedicate at least one node (or node group) to PostgreSQL with local SSD storage and a taint that excludes non-database workloads. Spark and Dagster get their own node pool. This prevents the most common production issue: Spark consuming all available memory on a shared node, causing PostgreSQL to OOM or swap.

**Implementation pointer:** Node pools, taints, affinities, and storage classes are Kubernetes infrastructure concerns. Configure in your cluster provisioning (Terraform, eksctl, GKE config) and reference in your PostgreSQL deployment manifests.

---

## 9. Index Hygiene

**Decision:** How do you detect and manage unused, duplicate, and bloated indexes before they dominate storage and slow down writes?

**Triggers:**
- Index storage exceeds table data storage (visible in `pg_stat_user_tables`)
- Write-heavy operations (bulk loads, Spark materializations) are slower than expected
- `pg_stat_user_indexes` shows indexes with zero or near-zero `idx_scan` counts over a multi-week window
- You've accumulated indexes from development/experimentation that production queries don't use

**Audit process:**

```sql
-- Find unused indexes (zero scans since last stats reset).
-- Run this AFTER your database has been serving production traffic
-- for at least 2 weeks. Dev-only indexes will show zero scans.
SELECT
    schemaname, tablename, indexname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelid NOT IN (
      SELECT conindid FROM pg_constraint
      WHERE contype IN ('p', 'u')  -- skip primary keys and unique constraints
  )
ORDER BY pg_relation_size(indexrelid) DESC;

-- Find duplicate indexes (same columns, same order).
SELECT
    a.indexrelid::regclass AS index_a,
    b.indexrelid::regclass AS index_b,
    pg_size_pretty(pg_relation_size(a.indexrelid)) AS size_a
FROM pg_index a
JOIN pg_index b ON a.indrelid = b.indrelid
    AND a.indexrelid < b.indexrelid
    AND a.indkey::text = b.indkey::text
WHERE a.indrelid::regclass::text NOT LIKE 'pg_%';
```

**Default-safe recommendation:** Run the unused-index audit quarterly. Before dropping any index:
1. Confirm zero scans over a representative traffic window (not just overnight)
2. Check that no index is required by a unique or foreign key constraint
3. Drop with `CONCURRENTLY` to avoid locking the table
4. Monitor query performance for 48 hours after dropping

For bloated indexes, `REINDEX CONCURRENTLY` is safe in PostgreSQL 14+ and doesn't lock the table.

**Implementation pointer:** Index auditing is an operational runbook in your team's playbook. Consider scheduling the audit query as a Dagster sensor or cron job that alerts when unused index storage exceeds a threshold.

---

## 10. Scale Targets and Tier Triggers

**Decision:** At what thresholds should you move from one operational tier to the next?

These are guidelines, not bright lines — your specific query patterns, hardware, and latency requirements will shift them. The goal is to give adopters a rough map so they can plan ahead rather than react to outages.

| Signal | Threshold (approximate) | Action |
|--------|------------------------|--------|
| Database size | > 50 GB | Enable WAL archiving and automated backups if not already (§2) |
| Database size | > 200 GB | Evaluate partitioning for largest tables (§4); consider connection pooling (§3) |
| Database size | > 1 TB | HA topology is strongly recommended (§1); cold-tier strategy needed (§5) |
| Connection count | > 80% of `max_connections` | Deploy PgBouncer (§3) or increase `max_connections` (but prefer pooling) |
| Write contention | Materialization jobs visibly slow down read queries | Read replica for Django/API traffic (§6); dedicated database node (§8) |
| Index storage | > 50% of table data storage | Run index hygiene audit (§9) |
| WAL generation rate | > 1 GB/hour sustained | Ensure WAL archive target can keep up; evaluate whether bulk loads should use `COPY` with `wal_level=minimal` in a maintenance window |
| Restore time | > RTO | More frequent base backups; consider CNPG with continuous archiving (§1, §2) |
| Historical partitions | Queried < 1% of the time | Stop materializing to PostGIS; query via Delta Lake (§5) |

**Default-safe recommendation:** Most SW adopters will operate comfortably in the sub-200 GB range for months or years. The single-node `docker-compose.yml` setup handles this well. Start planning for the next tier when you consistently see two or more of the signals above. The cheapest intervention is almost always "stop putting old data in PostGIS" (§5) — it reduces database size, index bloat, and write contention simultaneously.

---

## 11. Warehouse Observability

**Decision:** How do you monitor materialization health, replication lag, and cross-tier parity?

**Triggers:**
- Materialization jobs complete but produce row-count mismatches between Delta Lake and PostGIS
- Logical replication slots fall behind, causing stale downstream data
- You need an audit trail of what was materialized, when, and whether it matched

**Implementation:** SW ships three monitoring models in `warehouse/models/monitoring.py`:

| Model | Table | Purpose |
|---|---|---|
| `MaterializationRecord` | `sw_monitoring_materialization` | Per-asset parity record after each PostGIS materialization |
| `ReplicationLagSnapshot` | `sw_monitoring_replication_lag` | Periodic capture of logical replication slot lag |
| `ParityCheck` | `sw_monitoring_parity_check` | Cross-tier row count reconciliation |

`postgis_materialization_asset` automatically writes a `MaterializationRecord` after each successful write, capturing source/target row counts, duration, and the Dagster run ID. The `replication_lag_monitor` Dagster sensor polls `pg_replication_slots` every 60 seconds and writes `ReplicationLagSnapshot` rows.

**SLO templates (adapt to your deployment):**

| Metric | Target | Alert threshold | Query |
|---|---|---|---|
| Materialization parity | 100% `is_parity=True` | Any `is_parity=False` in the last 24h | `SELECT * FROM sw_monitoring_materialization WHERE NOT is_parity AND materialized_at > now() - interval '24 hours'` |
| Replication lag | < 100 MB | `lag_bytes > 100000000` sustained for 5 min | `SELECT * FROM sw_monitoring_replication_lag WHERE lag_bytes > 100000000 AND captured_at > now() - interval '5 minutes'` |
| Parity check pass rate | 100% `is_match=True` | Any `is_match=False` in the last check window | `SELECT * FROM sw_monitoring_parity_check WHERE NOT is_match AND checked_at > now() - interval '24 hours'` |

**postgres_exporter integration:** If you run `postgres_exporter` for Prometheus/Grafana, add custom queries against the `sw_monitoring_*` tables to surface these metrics alongside standard PostgreSQL metrics. Example collector config:

```yaml
sw_materialization_mismatches:
  query: "SELECT count(*) AS mismatch_count FROM sw_monitoring_materialization WHERE NOT is_parity AND materialized_at > now() - interval '1 hour'"
  metrics:
    - mismatch_count:
        usage: "GAUGE"
        description: "Materialization parity failures in the last hour"
sw_replication_lag:
  query: "SELECT slot_name, lag_bytes FROM sw_monitoring_replication_lag WHERE captured_at = (SELECT max(captured_at) FROM sw_monitoring_replication_lag)"
  metrics:
    - lag_bytes:
        usage: "GAUGE"
        description: "Latest replication lag in bytes per slot"
```

**Default-safe recommendation:** The monitoring tables and automated recording are enabled by default. For alerting, start with a simple Dagster sensor or cron job that checks for `is_parity=False` or `lag_bytes` above threshold and posts to your notification channel. Graduate to postgres_exporter + Grafana when you have a metrics stack.

---

## Further Reading

- [`docs/architecture.md`](architecture.md) — three-tier warehouse pattern, design-order constraints
- [`docs/quickstart.md`](quickstart.md) — single-node dev setup
- [`docs/orchestration/`](orchestration/) — Dagster asset graphs, scheduling, how-to-operate
- [`docs/warehouse-schema-evolution.md`](warehouse-schema-evolution.md) — schema migration playbook
