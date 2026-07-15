#!/usr/bin/env bash
# Per-partition pg_dump template for analytical DB spawns.
#
# Dumps a single partition (or set of partitions) from the hub and
# restores to a target analytical database. Designed for per-engagement
# or per-cycle snapshots.
#
# Usage:
#   ./pg-dump-partition.sh \
#     --source-host primary-host \
#     --source-db socialwarehouse \
#     --target-host analytical-host \
#     --target-db engagement_tx_2024 \
#     --tables "sw_fact_vote_history_2024,sw_fact_person_score_2024"
#
# Prerequisites:
#   - pg_dump and pg_restore installed (same major version as source)
#   - Network access from dump host to both source and target
#   - PGPASSWORD or .pgpass configured for both connections

set -euo pipefail

SOURCE_HOST=""
SOURCE_PORT="5432"
SOURCE_DB="socialwarehouse"
SOURCE_USER="socialwarehouse"
TARGET_HOST=""
TARGET_PORT="5432"
TARGET_DB=""
TARGET_USER="socialwarehouse"
TABLES=""
DUMP_DIR="/tmp/sw-partition-dump"
PARALLEL_JOBS=4

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-host) SOURCE_HOST="$2"; shift 2 ;;
        --source-port) SOURCE_PORT="$2"; shift 2 ;;
        --source-db)   SOURCE_DB="$2";   shift 2 ;;
        --source-user) SOURCE_USER="$2"; shift 2 ;;
        --target-host) TARGET_HOST="$2"; shift 2 ;;
        --target-port) TARGET_PORT="$2"; shift 2 ;;
        --target-db)   TARGET_DB="$2";   shift 2 ;;
        --target-user) TARGET_USER="$2"; shift 2 ;;
        --tables)      TABLES="$2";      shift 2 ;;
        --dump-dir)    DUMP_DIR="$2";    shift 2 ;;
        --jobs)        PARALLEL_JOBS="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$SOURCE_HOST" || -z "$TARGET_HOST" || -z "$TARGET_DB" || -z "$TABLES" ]]; then
    echo "Required: --source-host, --target-host, --target-db, --tables" >&2
    exit 1
fi

mkdir -p "$DUMP_DIR"

IFS=',' read -ra TABLE_ARRAY <<< "$TABLES"
TABLE_FLAGS=""
for t in "${TABLE_ARRAY[@]}"; do
    TABLE_FLAGS="$TABLE_FLAGS --table=$t"
done

echo "[$(date -Iseconds)] Dumping ${#TABLE_ARRAY[@]} table(s) from $SOURCE_HOST:$SOURCE_PORT/$SOURCE_DB..."

pg_dump \
    --host="$SOURCE_HOST" \
    --port="$SOURCE_PORT" \
    --username="$SOURCE_USER" \
    --dbname="$SOURCE_DB" \
    --format=directory \
    --jobs="$PARALLEL_JOBS" \
    --no-owner \
    --no-privileges \
    $TABLE_FLAGS \
    --file="$DUMP_DIR"

echo "[$(date -Iseconds)] Dump complete. Restoring to $TARGET_HOST:$TARGET_PORT/$TARGET_DB..."

# Dimension tables (required for FK references) should already exist
# on the target. If not, dump and restore them first.

pg_restore \
    --host="$TARGET_HOST" \
    --port="$TARGET_PORT" \
    --username="$TARGET_USER" \
    --dbname="$TARGET_DB" \
    --jobs="$PARALLEL_JOBS" \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    "$DUMP_DIR"

echo "[$(date -Iseconds)] Restore complete."

# Row count verification
echo "[$(date -Iseconds)] Verifying row counts..."
for t in "${TABLE_ARRAY[@]}"; do
    SOURCE_COUNT=$(psql -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" -tAc "SELECT count(*) FROM $t")
    TARGET_COUNT=$(psql -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TARGET_DB" -tAc "SELECT count(*) FROM $t")
    if [[ "$SOURCE_COUNT" == "$TARGET_COUNT" ]]; then
        echo "  [PARITY] $t: $SOURCE_COUNT rows"
    else
        echo "  [MISMATCH] $t: source=$SOURCE_COUNT target=$TARGET_COUNT" >&2
    fi
done

rm -rf "$DUMP_DIR"
echo "[$(date -Iseconds)] Done."
