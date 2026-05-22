"""
TargetSmart silver build: bronze.voter_file_ts -> silver.persons.

Reads bronze rows (each a JSON-stringified TS payload), maps TS fields
to canonical columns per `mappings.TS_TO_CANONICAL`, stashes unmapped
TS columns in `vendor_extras`, and upserts silver.persons on the
natural key (vendor='ts', vendor_voter_id).

This sub-issue covers persons only. Score extraction (silver.person_scores)
and vote-history extraction (silver.vote_history + denormalized
aggregates on silver.persons) are follow-on sub-issues B.2 and B.3.

Address resolution (silver.persons.address_id) is also deferred (B.4).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from swh.voters.ts.bronze import TS_VOTER_ID_COLUMN
from swh.voters.ts.mappings import TS_TO_CANONICAL

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


VENDOR = "ts"

# Canonical fields whose value should be cast from string to bool.
_BOOL_FIELDS = {"is_head_of_household"}
# Canonical fields whose value should be cast from string to int.
_INT_FIELDS = {"household_size"}
# Canonical fields whose value should be cast from string to float.
_FLOAT_FIELDS = {"latitude", "longitude"}


def _coerce(value: str, target_field: str) -> Any:
    """Type-coerce a stringified TS value into the canonical column type.

    Empty strings become None; coercion errors fall through to None
    (silver tolerates nulls; bronze preserves the original).
    """
    if value is None or value == "":
        return None
    if target_field in _BOOL_FIELDS:
        lowered = value.strip().lower()
        return lowered in ("1", "true", "t", "yes", "y")
    if target_field in _INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if target_field in _FLOAT_FIELDS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return value


def _map_raw_to_canonical(raw: dict, registration_state_default: str) -> dict:
    """Map one TS row dict (parsed from bronze.raw) to canonical fields.

    Returns a dict matching the silver.persons schema (minus the
    natural-key fields which the caller supplies). Unmapped TS columns
    accumulate in `vendor_extras`.
    """
    canonical: dict[str, Any] = {field: None for field in TS_TO_CANONICAL.values() if field}
    extras: dict[str, str] = {}

    for ts_field, value in raw.items():
        if value is None:
            value = ""
        if ts_field == TS_VOTER_ID_COLUMN:
            continue  # natural key handled separately
        target = TS_TO_CANONICAL.get(ts_field)
        if target is None:
            # Unmapped or explicitly-excluded (mapping value None).
            if ts_field in TS_TO_CANONICAL:
                continue  # explicit exclusion (PII opt-out, etc.)
            extras[ts_field] = str(value)
            continue
        canonical[target] = _coerce(str(value), target)

    # vendor_state mirrors registration_state per the importer convention.
    if not canonical.get("vendor_state"):
        canonical["vendor_state"] = canonical.get("registration_state") or registration_state_default

    # registration_state must be non-null per silver schema; default to the
    # bronze partition value if TS omitted vb.vf_source_state.
    if not canonical.get("registration_state"):
        canonical["registration_state"] = registration_state_default

    canonical["vendor_extras"] = extras
    return canonical


def build_silver_persons(
    spark: "SparkSession",
    bronze_table_key: str = "bronze.voter_file_ts",
    silver_table_key: str = "silver.persons",
) -> int:
    """Read bronze.voter_file_ts and upsert silver.persons.

    Upsert is on (vendor, vendor_voter_id). Re-running this function
    is idempotent at silver (last bronze row wins per natural key).

    Args:
        spark: Active SparkSession with Delta extensions registered.
        bronze_table_key: Registry key for the bronze table (overridable
            for tests).
        silver_table_key: Registry key for the silver table.

    Returns:
        Number of silver rows written (== distinct vendor_voter_ids in
        the bronze input).
    """
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        MapType,
        StringType,
        StructField,
        StructType,
    )

    from socialwarehouse.delta.tables import TABLES, SILVER_PERSONS

    bronze_path = TABLES[bronze_table_key]["path"]
    silver_path = TABLES[silver_table_key]["path"]
    silver_built_at = datetime.now(tz=timezone.utc)

    bronze_df = spark.read.format("delta").load(bronze_path)

    # Process in driver memory: collect, map, re-parallelize. This works
    # for state-sized loads (~5-15M rows); a chunked version is a
    # follow-on if scale demands it. The simpler shape ships first.
    rows = bronze_df.select(
        "vendor_voter_id",
        "state_abbreviation",
        "raw",
        "source_file",
        "ingested_at",
    ).collect()

    silver_records = []
    seen_voter_ids: set[str] = set()
    # Bronze is append-only; dedup at silver build time so we don't write
    # the same natural key twice in a single batch.
    for r in rows:
        vid = r["vendor_voter_id"]
        if vid in seen_voter_ids:
            continue  # last-write-wins handled below; this is intra-batch dedup
        seen_voter_ids.add(vid)
        try:
            raw_payload = json.loads(r["raw"])
        except (TypeError, json.JSONDecodeError):
            logger.warning("Skipping bronze row with unparseable raw: %s", vid)
            continue
        canonical = _map_raw_to_canonical(raw_payload, r["state_abbreviation"])
        silver_records.append({
            "vendor": VENDOR,
            "vendor_voter_id": vid,
            "person_key": f"{VENDOR}:{vid}",
            **canonical,
            "source_file": r["source_file"],
            "ingested_at": r["ingested_at"],
            "silver_built_at": silver_built_at,
        })

    if not silver_records:
        logger.info("build_silver_persons: no bronze rows; nothing to write.")
        return 0

    silver_df = spark.createDataFrame(silver_records, schema=SILVER_PERSONS)

    if DeltaTable.isDeltaTable(spark, silver_path):
        silver_table = DeltaTable.forPath(spark, silver_path)
        (
            silver_table.alias("tgt")
            .merge(
                silver_df.alias("src"),
                "tgt.vendor = src.vendor AND tgt.vendor_voter_id = src.vendor_voter_id",
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        # Schema-creation case (bootstrap); follow registry partitioning.
        partition_by = TABLES[silver_table_key].get("partition_by", [])
        writer = silver_df.write.format("delta")
        if partition_by:
            writer = writer.partitionBy(*partition_by)
        writer.mode("overwrite").save(silver_path)

    n = len(silver_records)
    logger.info("build_silver_persons: wrote %d silver rows.", n)
    return n
