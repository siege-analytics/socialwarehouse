# Point-in-Time Recovery (PITR) Restore Runbook

This runbook covers end-to-end point-in-time recovery for a SocialWarehouse deployment running on CloudNativePG (CNPG). It assumes the CNPG manifests from `k8s/cnpg/` are deployed with WAL archiving enabled.

## Prerequisites

- CNPG operator installed on the Kubernetes cluster
- WAL archiving to S3-compatible storage is configured and healthy
- At least one successful base backup exists (check with `kubectl cnpg backup list`)
- `kubectl` and `kubectl-cnpg` plugin installed locally

## When to use PITR

- **Data corruption**: accidental DELETE, UPDATE, or DROP without WHERE clause
- **Application bug**: code deployed that wrote incorrect data
- **Schema corruption**: migration that broke the schema in a way that can't be rolled back
- **Compliance**: need to produce a snapshot of data at a specific point in time

PITR is NOT a substitute for logical backups (`pg_dump`). Use PITR for operational recovery; use logical backups for long-term archival and cross-version migration.

## Step 1: Identify the target timestamp

Determine the exact timestamp to recover to. This should be the moment just **before** the incident.

```bash
# Check recent WAL archive status
kubectl cnpg status socialwarehouse-postgis

# If the incident is recent, check PostgreSQL logs for the exact timestamp
kubectl logs socialwarehouse-postgis-1 --tail=200 | grep -i "error\|drop\|delete\|truncate"

# If you know the approximate time, use pg_stat_activity on a standby
kubectl exec socialwarehouse-postgis-2 -- psql -U socialwarehouse -c \
  "SELECT query_start, query FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start DESC LIMIT 20;"
```

Record the target timestamp in UTC. Example: `2026-06-08T14:30:00Z`

## Step 2: Verify WAL archive coverage

Confirm that WAL archives cover the target timestamp:

```bash
# Check the oldest and newest archived WAL segments
kubectl cnpg status socialwarehouse-postgis --verbose

# The "First Available Backup" and "Latest Backup" fields show coverage.
# PITR requires: oldest backup < target timestamp < latest WAL
```

If WAL archives don't cover the target timestamp, PITR is not possible. Fall back to the nearest base backup.

## Step 3: Create a recovery Cluster

Create a new CNPG Cluster that bootstraps from the WAL archive at the target timestamp:

```yaml
# pitr-recovery.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: socialwarehouse-postgis-recovered
  labels:
    app.kubernetes.io/name: socialwarehouse
    app.kubernetes.io/component: database-recovery
spec:
  instances: 1  # single instance for recovery verification

  imageName: ghcr.io/cloudnative-pg/postgis:16-3.4

  bootstrap:
    recovery:
      source: socialwarehouse-postgis
      recoveryTarget:
        targetTime: "2026-06-08T14:30:00Z"  # <-- your target timestamp

  externalClusters:
    - name: socialwarehouse-postgis
      barmanObjectStore:
        destinationPath: s3://socialwarehouse-backups/wal/
        endpointURL: http://minio:9000      # remove for real S3
        s3Credentials:
          accessKeyId:
            name: minio-credentials
            key: ACCESS_KEY_ID
          secretAccessKey:
            name: minio-credentials
            key: SECRET_ACCESS_KEY

  storage:
    size: 100Gi
    storageClass: gp3
```

Apply and wait for recovery:

```bash
kubectl apply -f pitr-recovery.yaml

# Watch recovery progress
kubectl cnpg status socialwarehouse-postgis-recovered -w

# Recovery is complete when the cluster reports "Cluster in healthy state"
```

## Step 4: Verify data integrity

Before promoting the recovered instance, verify the data is correct:

```bash
# Connect to the recovered instance
kubectl exec -it socialwarehouse-postgis-recovered-1 -- psql -U socialwarehouse

# Run parity checks against known-good counts
# (record these counts BEFORE the incident if possible)
SELECT 'sw_dim_person' AS table_name, count(*) FROM sw_dim_person
UNION ALL SELECT 'sw_dim_geography', count(*) FROM sw_dim_geography
UNION ALL SELECT 'sw_fact_vote_history', count(*) FROM sw_fact_vote_history
UNION ALL SELECT 'sw_fact_person_score', count(*) FROM sw_fact_person_score;

# Check for the specific data that was corrupted
# (tailor this to your incident)

# Verify PostGIS extensions are intact
SELECT PostGIS_Version();

# Verify partitioned tables are intact
SELECT
    parent.relname AS parent,
    count(*) AS partition_count
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
GROUP BY parent.relname
ORDER BY parent.relname;
```

## Step 5: Promote or cutover

### Option A: Promote the recovered instance (replace the original)

```bash
# Scale down the original cluster to avoid split-brain
kubectl scale cluster socialwarehouse-postgis --replicas=0

# Scale up the recovered cluster to production size
kubectl patch cluster socialwarehouse-postgis-recovered \
  --type merge -p '{"spec":{"instances":3}}'

# Update your application's connection string to point to the recovered cluster
# (PgBouncer config, Django DATABASES, Dagster resources)
```

### Option B: Export specific tables from the recovered instance

If only specific data was corrupted, export just those tables:

```bash
# Dump the corrected tables from the recovered instance
kubectl exec socialwarehouse-postgis-recovered-1 -- \
  pg_dump -U socialwarehouse -t sw_dim_person --format=custom \
  > /tmp/sw_dim_person_recovered.dump

# Restore to the original (after fixing the root cause)
kubectl exec -i socialwarehouse-postgis-1 -- \
  pg_restore -U socialwarehouse --clean --if-exists -d socialwarehouse \
  < /tmp/sw_dim_person_recovered.dump
```

### Option C: Rename and swap (zero-downtime for Kubernetes)

```bash
# Rename recovered cluster to match the original service name
# This requires editing the Cluster CRD and restarting pods
# Detailed steps depend on your ingress/service mesh configuration
```

## Step 6: Post-recovery cleanup

```bash
# Once the recovered cluster is promoted and verified:

# 1. Delete the old cluster (if replaced)
kubectl delete cluster socialwarehouse-postgis

# 2. Rename the recovered cluster (optional)
# kubectl patch cluster socialwarehouse-postgis-recovered ...

# 3. Re-enable WAL archiving on the new primary
# (CNPG handles this automatically if backup config is in the Cluster CRD)

# 4. Run a fresh base backup
kubectl cnpg backup socialwarehouse-postgis-recovered

# 5. Verify WAL archiving is working
kubectl cnpg status socialwarehouse-postgis-recovered

# 6. Record the incident and recovery in your ops log
```

## Monthly test-restore validation

Schedule a monthly test restore to verify that your backup pipeline works end-to-end. A backup that hasn't been tested is not a backup.

### Procedure

```bash
# 1. Note the current timestamp
TARGET_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# 2. Create a test-recovery cluster (use the template above with a unique name)
# Replace targetTime with $TARGET_TS

# 3. Wait for recovery to complete
kubectl cnpg status socialwarehouse-postgis-test-restore -w

# 4. Run the verification queries from Step 4

# 5. Record results: date, target timestamp, recovery time, parity pass/fail

# 6. Delete the test cluster
kubectl delete cluster socialwarehouse-postgis-test-restore
```

### Success criteria

- Recovery completes within your RTO (recovery time objective)
- All parity checks pass against the production cluster's row counts
- PostGIS extensions and partitioned tables are intact
- No data loss detected between the target timestamp and the last WAL

### Failure modes to watch for

| Symptom | Likely cause | Fix |
|---|---|---|
| "WAL file not found" | WAL archiving gap | Investigate `barmanObjectStore` configuration; check S3 bucket permissions |
| Recovery hangs | Large WAL replay volume | Wait longer; check I/O throughput on the recovery pod |
| Missing PostGIS extension | Image mismatch | Ensure recovery uses the same PostGIS image as production |
| Partition count mismatch | Partitions created after the target timestamp | Expected — only partitions that existed at the target timestamp are recovered |
| "Could not connect to source" | S3 credentials expired | Rotate credentials in the minio-credentials Secret |

## Further reading

- [CloudNativePG Recovery documentation](https://cloudnative-pg.io/documentation/current/recovery/)
- `k8s/cnpg/README.md` — CNPG quick-start and customization
- `docs/production-operations.md` §1 (HA topology), §2 (backup/PITR)
- `docs/backfill-playbook.md` — for rebuilding data after recovery
