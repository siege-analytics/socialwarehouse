"""
TS score extraction: bronze.voter_file_ts -> silver.person_scores.

Reads bronze rows, parses each `raw` JSON payload, and emits one
silver.person_scores row per recognized TS score column.

Idempotent: re-running upserts on the natural key
(person_key, score_type, source_vendor, methodology_version).
Unmapped score-shaped columns stay in vendor_extras (no warning per-row
to keep logs sane; the registered TS score columns are documented in
docs/entities/fact-person-score.md).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from swh.voters.ts.score_mappings import CYCLE_PREFIXES, lookup

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

VENDOR = "ts"
DEFAULT_METHODOLOGY = "ts-2024"


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_rows_from_raw(
    raw: dict,
    person_key: str,
    scored_at: datetime,
    loaded_at: datetime,
    default_methodology: str,
) -> list[dict]:
    """Emit silver.person_scores row-dicts for known score columns in raw.

    Static + cycle-aligned TS score columns are both handled via the
    `lookup` helper from score_mappings.
    """
    rows: list[dict] = []
    for col, value in raw.items():
        # Quick reject: only consider columns that COULD be a score.
        if not (col.endswith("_score") or any(col.startswith(p) for p in CYCLE_PREFIXES)):
            continue
        resolved = lookup(col, default_methodology)
        if resolved is None:
            continue
        score_type, methodology_version = resolved
        v = _safe_float(value)
        if v is None:
            continue
        rows.append({
            "person_key": person_key,
            "score_type": score_type,
            "value": v,
            "source_vendor": VENDOR,
            "methodology_version": methodology_version,
            "scored_at": scored_at,
            "loaded_at": loaded_at,
        })
    return rows


def extract_scores(
    spark: "SparkSession",
    bronze_table_key: str = "bronze.voter_file_ts",
    silver_table_key: str = "silver.person_scores",
    default_methodology: str = DEFAULT_METHODOLOGY,
) -> int:
    """Read bronze.voter_file_ts and upsert silver.person_scores.

    Args:
        spark: Active SparkSession with Delta extensions registered.
        bronze_table_key: Registry key for the bronze table.
        silver_table_key: Registry key for the silver score table.
        default_methodology: Methodology label for static (non-cycle)
            TS scores. Cycle-aligned scores embed the cycle year.

    Returns:
        Number of silver score rows written.
    """
    from delta.tables import DeltaTable

    from socialwarehouse.delta.tables import SILVER_PERSON_SCORES, TABLES

    bronze_path = TABLES[bronze_table_key]["path"]
    silver_path = TABLES[silver_table_key]["path"]
    loaded_at = datetime.now(tz=timezone.utc)

    bronze_df = spark.read.format("delta").load(bronze_path)
    rows = bronze_df.select(
        "vendor_voter_id", "raw", "ingested_at"
    ).collect()

    score_records: list[dict] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for r in rows:
        vid = r["vendor_voter_id"]
        if not vid:
            continue
        person_key = f"{VENDOR}:{vid}"
        scored_at = r["ingested_at"]
        try:
            payload = json.loads(r["raw"])
        except (TypeError, json.JSONDecodeError):
            continue
        for row in _score_rows_from_raw(payload, person_key, scored_at, loaded_at, default_methodology):
            key = (row["person_key"], row["score_type"],
                   row["source_vendor"], row["methodology_version"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            score_records.append(row)

    if not score_records:
        logger.info("extract_scores: no scores in bronze; nothing to write.")
        return 0

    score_df = spark.createDataFrame(score_records, schema=SILVER_PERSON_SCORES)

    if DeltaTable.isDeltaTable(spark, silver_path):
        tgt = DeltaTable.forPath(spark, silver_path)
        (
            tgt.alias("t")
            .merge(
                score_df.alias("s"),
                "t.person_key = s.person_key AND "
                "t.score_type = s.score_type AND "
                "t.source_vendor = s.source_vendor AND "
                "t.methodology_version = s.methodology_version",
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        partition_by = TABLES[silver_table_key].get("partition_by", [])
        writer = score_df.write.format("delta")
        if partition_by:
            writer = writer.partitionBy(*partition_by)
        writer.mode("overwrite").save(silver_path)

    logger.info("extract_scores: wrote %d silver score rows.", len(score_records))
    return len(score_records)
