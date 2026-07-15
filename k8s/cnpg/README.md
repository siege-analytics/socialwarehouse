# CloudNativePG Deployment

Production-ready PostgreSQL + PostGIS on Kubernetes using CloudNativePG (CNPG).

## Prerequisites

1. Kubernetes cluster (1.25+)
2. CNPG operator installed:
   ```bash
   kubectl apply --server-side -f \
     https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.0.yaml
   ```

## Quick start (dev with MinIO)

```bash
# Deploy MinIO for local WAL archiving
kubectl apply -f minio.yaml

# Wait for MinIO and bucket creation
kubectl wait --for=condition=complete job/minio-create-bucket --timeout=60s

# Deploy the CNPG cluster
kubectl apply -f cluster.yaml

# Deploy scheduled backups
kubectl apply -f backup-schedule.yaml

# Watch cluster come up (primary + 2 standbys)
kubectl get cluster socialwarehouse-postgis -w
```

## Production customization

### Storage

Replace `storageClass: gp3` with your cluster's provisioned-IOPS storage class. Use local NVMe SSDs for lowest latency.

### WAL archiving

Replace the MinIO endpoint in `cluster.yaml` with your S3/GCS/Azure Blob configuration:

```yaml
backup:
  barmanObjectStore:
    destinationPath: s3://your-bucket/wal/
    # Remove endpointURL for real AWS S3
    s3Credentials:
      accessKeyId:
        name: your-aws-secret
        key: ACCESS_KEY_ID
      secretAccessKey:
        name: your-aws-secret
        key: SECRET_ACCESS_KEY
```

### Memory tuning

The `postgresql.parameters` block in `cluster.yaml` ships with staging-tier defaults (16 GB RAM). Adjust per the profiles in `docs/production-operations.md` section 3.

### Scaling

- **Standbys**: Change `instances` (minimum 2 for HA, 3 recommended)
- **Resources**: Adjust `resources.requests` and `resources.limits` to match your node size
- **Storage**: Increase `storage.size` as data grows

## Monitoring

The cluster ships with `enablePodMonitor: true`. If you run Prometheus Operator, CNPG metrics are scraped automatically. See `docs/production-operations.md` section 11 for observability integration.

## Recovery

### Point-in-time recovery

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: socialwarehouse-postgis-recovered
spec:
  instances: 3
  imageName: ghcr.io/cloudnative-pg/postgis:16-3.4
  bootstrap:
    recovery:
      source: socialwarehouse-postgis
      recoveryTarget:
        targetTime: "2026-01-15T12:00:00Z"
  externalClusters:
    - name: socialwarehouse-postgis
      barmanObjectStore:
        destinationPath: s3://socialwarehouse-backups/wal/
        s3Credentials:
          accessKeyId:
            name: minio-credentials
            key: ACCESS_KEY_ID
          secretAccessKey:
            name: minio-credentials
            key: SECRET_ACCESS_KEY
```

### Switchover (planned)

```bash
kubectl cnpg promote socialwarehouse-postgis <standby-pod-name>
```

## Further reading

- [CloudNativePG documentation](https://cloudnative-pg.io/documentation/)
- `docs/production-operations.md` sections 1 (HA topology) and 2 (backup/PITR)
