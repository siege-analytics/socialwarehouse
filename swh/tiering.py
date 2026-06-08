"""Partition tiering assessment for ``swh tier-status`` (#329).

Inspects partitioned fact tables and classifies each partition into
hot, warm, or cold based on its range boundary relative to the current
date and the configured hot window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Tier(Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class PartitionInfo:
    parent_table: str
    partition_name: str
    tier: Tier
    range_start: Optional[str]
    range_end: Optional[str]
    tablespace: str
    size_bytes: int
    index_count: int
    is_default: bool

    @property
    def size_pretty(self) -> str:
        from swh.audit_indexes import pretty_size
        return pretty_size(self.size_bytes)

    @property
    def recommended_tablespace(self) -> str:
        return {"hot": "pg_default", "warm": "warm_ts", "cold": "cold_ts"}[self.tier.value]

    @property
    def needs_move(self) -> bool:
        if self.is_default:
            return False
        return self.tablespace != self.recommended_tablespace


PARTITIONED_TABLES_SQL = """\
SELECT
    nmsp_parent.nspname AS parent_schema,
    parent.relname AS parent_table,
    nmsp_child.nspname AS child_schema,
    child.relname AS partition_name,
    child.reltablespace,
    ts.spcname AS tablespace_name,
    pg_relation_size(child.oid) AS size_bytes,
    (SELECT count(*) FROM pg_index WHERE indrelid = child.oid) AS index_count,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bound
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
JOIN pg_namespace nmsp_parent ON parent.relnamespace = nmsp_parent.oid
JOIN pg_namespace nmsp_child ON child.relnamespace = nmsp_child.oid
LEFT JOIN pg_tablespace ts ON child.reltablespace = ts.oid
WHERE nmsp_parent.nspname = 'public'
  AND parent.relname = ANY(%s)
ORDER BY parent.relname, child.relname;
"""

PARTITIONED_FACT_TABLES = [
    "sw_fact_redistricting_plan",
    "sw_fact_vote_history",
    "sw_fact_person_score",
]


def _parse_range_year(partition_bound: str) -> Optional[int]:
    if partition_bound is None or "DEFAULT" in partition_bound.upper():
        return None
    import re
    match = re.search(r"FROM \('([^']+)'\)", partition_bound)
    if not match:
        return None
    val = match.group(1)
    try:
        if "-" in val:
            return int(val[:4])
        return int(val)
    except (ValueError, IndexError):
        return None


def _classify_tier(range_year: Optional[int], current_year: int, hot_window: int) -> Tier:
    if range_year is None:
        return Tier.HOT
    age = current_year - range_year
    if age <= hot_window:
        return Tier.HOT
    if age <= hot_window + 4:
        return Tier.WARM
    return Tier.COLD


def assess_tiers(
    dsn: str,
    *,
    hot_window: int = 1,
    reference_year: Optional[int] = None,
) -> list[PartitionInfo]:
    import psycopg2

    current_year = reference_year or date.today().year
    results: list[PartitionInfo] = []

    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        cur = conn.cursor()
        cur.execute(PARTITIONED_TABLES_SQL, (PARTITIONED_FACT_TABLES,))

        for (parent_schema, parent_table, child_schema, partition_name,
             reltablespace, tablespace_name, size_bytes, index_count,
             partition_bound) in cur.fetchall():

            is_default = partition_bound is not None and "DEFAULT" in partition_bound.upper()
            range_year = _parse_range_year(partition_bound)
            tier = _classify_tier(range_year, current_year, hot_window)

            range_start = None
            range_end = None
            if partition_bound and not is_default:
                import re
                from_match = re.search(r"FROM \('([^']+)'\)", partition_bound)
                to_match = re.search(r"TO \('([^']+)'\)", partition_bound)
                if from_match:
                    range_start = from_match.group(1)
                if to_match:
                    range_end = to_match.group(1)

            results.append(PartitionInfo(
                parent_table=parent_table,
                partition_name=partition_name,
                tier=tier,
                range_start=range_start,
                range_end=range_end,
                tablespace=tablespace_name or "pg_default",
                size_bytes=size_bytes,
                index_count=index_count,
                is_default=is_default,
            ))
    finally:
        conn.close()

    return results
