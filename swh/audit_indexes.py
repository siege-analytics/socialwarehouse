"""Index audit for ``swh audit-indexes`` (#333).

Detects unused, duplicate, and bloated indexes in the PostGIS tier
using pg_stat_user_indexes and pg_index catalog views.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Finding(Enum):
    UNUSED = "unused"
    DUPLICATE = "duplicate"
    BLOATED = "bloated"


@dataclass
class IndexIssue:
    finding: Finding
    schema_name: str
    table_name: str
    index_name: str
    index_size_bytes: int
    detail: str
    recommendation: str

    @property
    def index_size_pretty(self) -> str:
        return pretty_size(self.index_size_bytes)


def pretty_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


UNUSED_INDEX_SQL = """\
SELECT
    schemaname,
    relname AS tablename,
    indexrelname AS indexname,
    idx_scan,
    pg_relation_size(indexrelid) AS index_size_bytes
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelid NOT IN (
      SELECT conindid FROM pg_constraint
      WHERE contype IN ('p', 'u')
  )
ORDER BY pg_relation_size(indexrelid) DESC;
"""

DUPLICATE_INDEX_SQL = """\
SELECT
    a.indexrelid::regclass AS index_a,
    b.indexrelid::regclass AS index_b,
    a.indrelid::regclass AS tablename,
    pg_relation_size(a.indexrelid) AS size_a,
    pg_relation_size(b.indexrelid) AS size_b,
    n.nspname AS schemaname
FROM pg_index a
JOIN pg_index b ON a.indrelid = b.indrelid
    AND a.indexrelid < b.indexrelid
    AND a.indkey::text = b.indkey::text
JOIN pg_class c ON c.oid = a.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(a.indexrelid) DESC;
"""

BLOAT_ESTIMATE_SQL = """\
SELECT
    nspname AS schemaname,
    tblname AS tablename,
    idxname AS indexname,
    real_size AS index_size_bytes,
    CASE WHEN real_size > 0
         THEN round(100.0 * (real_size - estimated_size) / real_size, 1)
         ELSE 0
    END AS bloat_pct
FROM (
    SELECT
        n.nspname,
        ct.relname AS tblname,
        ci.relname AS idxname,
        pg_relation_size(ci.oid) AS real_size,
        COALESCE(
            (8192 * ci.relpages *
             CASE WHEN ct.reltuples > 0
                  THEN (ci.reltuples / ct.reltuples)
                  ELSE 1
             END)::bigint,
            pg_relation_size(ci.oid)
        ) AS estimated_size
    FROM pg_index i
    JOIN pg_class ci ON ci.oid = i.indexrelid
    JOIN pg_class ct ON ct.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = ct.relnamespace
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND pg_relation_size(ci.oid) > 0
) sub
WHERE real_size > 0
  AND (real_size - estimated_size) > 0
ORDER BY bloat_pct DESC;
"""


def audit_indexes(
    dsn: str,
    *,
    bloat_threshold_pct: float = 50.0,
    min_size_bytes: int = 1_048_576,
) -> list[IndexIssue]:
    import psycopg2

    issues: list[IndexIssue] = []
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        cur = conn.cursor()

        cur.execute(UNUSED_INDEX_SQL)
        for schema, table, index, scans, size_bytes in cur.fetchall():
            if size_bytes < min_size_bytes:
                continue
            issues.append(IndexIssue(
                finding=Finding.UNUSED,
                schema_name=schema,
                table_name=table,
                index_name=index,
                index_size_bytes=size_bytes,
                detail=f"{scans} scans since stats reset",
                recommendation=f"DROP INDEX CONCURRENTLY {index};",
            ))

        cur.execute(DUPLICATE_INDEX_SQL)
        for idx_a, idx_b, table, size_a, size_b, schema in cur.fetchall():
            issues.append(IndexIssue(
                finding=Finding.DUPLICATE,
                schema_name=schema,
                table_name=str(table),
                index_name=str(idx_b),
                index_size_bytes=size_b,
                detail=f"duplicates {idx_a}",
                recommendation=f"DROP INDEX CONCURRENTLY {idx_b};",
            ))

        cur.execute(BLOAT_ESTIMATE_SQL)
        for schema, table, index, size_bytes, bloat_pct in cur.fetchall():
            if bloat_pct < bloat_threshold_pct or size_bytes < min_size_bytes:
                continue
            issues.append(IndexIssue(
                finding=Finding.BLOATED,
                schema_name=schema,
                table_name=table,
                index_name=index,
                index_size_bytes=size_bytes,
                detail=f"{bloat_pct}% estimated bloat",
                recommendation=f"REINDEX INDEX CONCURRENTLY {index};",
            ))
    finally:
        conn.close()

    return issues
