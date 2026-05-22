"""
TS vote-history extraction: bronze.voter_file_ts -> silver.vote_history.

Parses per-cycle TS columns (vb.vf_g_<year>, vb.vf_p_<year>) into
individual silver.vote_history rows. Method columns
(vb.vf_g_method_<year>, vb.vf_p_method_<year>) are paired with their
participation columns and supply voted_method.

Compute_aggregates recomputes the denormalized aggregate columns on
silver.persons (general_election_count, primary_election_count,
total_vote_count, last_voted_at, vote_frequency_category) from
silver.vote_history.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from swh.voters.ts.vote_history_mappings import (
    canonical_method,
    election_date_for,
    is_voted,
    parse_column,
    vote_frequency_category,
)

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

VENDOR = "ts"


def _vote_history_rows_from_raw(
    raw: dict,
    person_key: str,
    loaded_at: datetime,
) -> list[dict]:
    """Emit silver.vote_history row-dicts from a parsed TS payload.

    Method columns are paired with participation columns by year. A
    participation column with no matching method column gets
    voted_method='unknown'.
    """
    # First pass: collect participation events per (etype, year).
    participated: dict[tuple[str, int], bool] = {}
    methods: dict[tuple[str, int], str] = {}
    for col, value in raw.items():
        parsed = parse_column(col)
        if parsed is None:
            continue
        etype, year, is_method = parsed
        key = (etype, year)
        if is_method:
            methods[key] = canonical_method(value)
        else:
            if is_voted(value):
                participated[key] = True

    rows: list[dict] = []
    for (etype, year), _ in participated.items():
        rows.append({
            "person_key": person_key,
            "election_date": election_date_for(etype, year),
            "election_year": year,
            "election_type": etype,
            "voted_method": methods.get((etype, year), "unknown"),
            "source_vendor": VENDOR,
            "loaded_at": loaded_at,
        })
    return rows


def extract_vote_history(
    spark: "SparkSession",
    bronze_table_key: str = "bronze.voter_file_ts",
    silver_table_key: str = "silver.vote_history",
) -> int:
    """Read bronze.voter_file_ts and upsert silver.vote_history.

    Args:
        spark: Active SparkSession with Delta extensions.
        bronze_table_key: Registry key for the bronze table.
        silver_table_key: Registry key for the silver vote-history table.

    Returns:
        Number of silver vote-history rows written.
    """
    from delta.tables import DeltaTable

    from socialwarehouse.delta.tables import SILVER_VOTE_HISTORY, TABLES

    bronze_path = TABLES[bronze_table_key]["path"]
    silver_path = TABLES[silver_table_key]["path"]
    loaded_at = datetime.now(tz=timezone.utc)

    bronze_df = spark.read.format("delta").load(bronze_path)
    rows = bronze_df.select("vendor_voter_id", "raw").collect()

    history_records: list[dict] = []
    seen_keys: set[tuple[str, "date", str, str]] = set()
    for r in rows:
        vid = r["vendor_voter_id"]
        if not vid:
            continue
        person_key = f"{VENDOR}:{vid}"
        try:
            payload = json.loads(r["raw"])
        except (TypeError, json.JSONDecodeError):
            continue
        for row in _vote_history_rows_from_raw(payload, person_key, loaded_at):
            key = (row["person_key"], row["election_date"],
                   row["election_type"], row["source_vendor"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            history_records.append(row)

    if not history_records:
        logger.info("extract_vote_history: no events found; nothing to write.")
        return 0

    history_df = spark.createDataFrame(history_records, schema=SILVER_VOTE_HISTORY)

    if DeltaTable.isDeltaTable(spark, silver_path):
        tgt = DeltaTable.forPath(spark, silver_path)
        (
            tgt.alias("t")
            .merge(
                history_df.alias("s"),
                "t.person_key = s.person_key AND "
                "t.election_date = s.election_date AND "
                "t.election_type = s.election_type AND "
                "t.source_vendor = s.source_vendor",
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        partition_by = TABLES[silver_table_key].get("partition_by", [])
        writer = history_df.write.format("delta")
        if partition_by:
            writer = writer.partitionBy(*partition_by)
        writer.mode("overwrite").save(silver_path)

    logger.info("extract_vote_history: wrote %d silver rows.", len(history_records))
    return len(history_records)


def compute_aggregates(
    spark: "SparkSession",
    silver_history_key: str = "silver.vote_history",
    silver_persons_key: str = "silver.persons",
) -> int:
    """Recompute aggregate counters on silver.persons from silver.vote_history.

    Updates: general_election_count, primary_election_count,
    total_vote_count, last_voted_at, vote_frequency_category.

    Args:
        spark: Active SparkSession.
        silver_history_key: Registry key for silver.vote_history.
        silver_persons_key: Registry key for silver.persons.

    Returns:
        Number of silver.persons rows updated.
    """
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        DateType,
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    from socialwarehouse.delta.tables import TABLES

    history_path = TABLES[silver_history_key]["path"]
    persons_path = TABLES[silver_persons_key]["path"]

    history = spark.read.format("delta").load(history_path)

    agg = (
        history
        .groupBy("person_key")
        .agg(
            F.sum(F.when(F.col("election_type") == "general", 1).otherwise(0)).alias("general_election_count"),
            F.sum(F.when(F.col("election_type") == "primary", 1).otherwise(0)).alias("primary_election_count"),
            F.count("*").alias("total_vote_count"),
            F.max("election_date").alias("last_voted_at"),
        )
    )
    rows = agg.collect()

    # Compute vote_frequency_category in driver and re-parallelize. Small N.
    agg_rows = []
    for r in rows:
        g = int(r["general_election_count"] or 0)
        t = int(r["total_vote_count"] or 0)
        agg_rows.append({
            "person_key": r["person_key"],
            "general_election_count": g,
            "primary_election_count": int(r["primary_election_count"] or 0),
            "total_vote_count": t,
            "last_voted_at": r["last_voted_at"],
            "vote_frequency_category": vote_frequency_category(g, t),
        })

    if not agg_rows:
        return 0

    agg_schema = StructType([
        StructField("person_key", StringType(), False),
        StructField("general_election_count", IntegerType(), True),
        StructField("primary_election_count", IntegerType(), True),
        StructField("total_vote_count", IntegerType(), True),
        StructField("last_voted_at", DateType(), True),
        StructField("vote_frequency_category", StringType(), True),
    ])
    agg_df = spark.createDataFrame(agg_rows, schema=agg_schema)

    persons = DeltaTable.forPath(spark, persons_path)
    (
        persons.alias("p")
        .merge(agg_df.alias("a"), "p.person_key = a.person_key")
        .whenMatchedUpdate(set={
            "general_election_count": "a.general_election_count",
            "primary_election_count": "a.primary_election_count",
            "total_vote_count": "a.total_vote_count",
            "last_voted_at": "a.last_voted_at",
            "vote_frequency_category": "a.vote_frequency_category",
        })
        .execute()
    )

    logger.info("compute_aggregates: updated %d silver.persons rows.", len(agg_rows))
    return len(agg_rows)
