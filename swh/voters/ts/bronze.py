"""
TargetSmart bronze ingest: CSV -> bronze.voter_file_ts (Delta).

Each CSV row is JSON-stringified and written to `bronze.voter_file_ts`
with `vendor_voter_id` extracted from `vb.voterbase_id` and
`state_abbreviation` from the operator-supplied --state arg. Append-only;
idempotency is enforced at the silver layer via natural-key upsert.

For the silver build that consumes this table, see
`swh.voters.ts.silver.build_silver_persons`.
"""

from __future__ import annotations

import csv as _csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from swh.voters._legacy_raw import (
    DEFAULT_CSV_ENCODING,
    TARGETSMART_DEFAULT_DTYPES,
)

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


# Column that holds the natural-key TS voter ID. Hoisted as a constant
# because the silver build also reads it; one source of truth.
TS_VOTER_ID_COLUMN = "vb.voterbase_id"


def ingest_bronze(
    spark: "SparkSession",
    csv_path: str | Path,
    state: str,
    source_file_name: str | None = None,
    chunk_size: int = 100_000,
) -> int:
    """Read a TargetSmart-format CSV and append rows to bronze.voter_file_ts.

    Each input row is JSON-stringified (preserving the full TS column set)
    and written with the natural-key voter id pulled out into its own
    column. State partition value is operator-supplied so this works on
    files that span multiple states (rare, but possible).

    Args:
        spark: Active SparkSession with Delta extensions registered.
        csv_path: Path to the TS CSV. utf-8-sig decoding handles the BOM
            many TS exports include.
        state: 2-char USPS state code; becomes the bronze partition key.
        source_file_name: Provenance label; defaults to basename(csv_path).
        chunk_size: Pandas read_csv chunksize; controls memory footprint.

    Returns:
        Number of rows appended to bronze.

    Raises:
        ValueError: state is not a 2-char string; CSV missing the
            vb.voterbase_id column.
    """
    if not isinstance(state, str) or len(state) != 2:
        raise ValueError(
            f"state must be a 2-char USPS code, got {state!r}. "
            f"Pass via --state TX (etc.) on the CLI."
        )

    import pandas as pd
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    from socialwarehouse.delta.tables import TABLES

    table_def = TABLES["bronze.voter_file_ts"]
    bronze_path = table_def["path"]
    bronze_schema = table_def["schema"]

    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    source = source_file_name or csv_path.name
    ingested_at = datetime.now(tz=timezone.utc)

    total = 0
    source_row_offset = 0

    for chunk in pd.read_csv(
        csv_path,
        chunksize=chunk_size,
        encoding=DEFAULT_CSV_ENCODING,
        dtype=TARGETSMART_DEFAULT_DTYPES,
        quoting=_csv.QUOTE_MINIMAL,
        keep_default_na=False,
        na_filter=False,
    ):
        if TS_VOTER_ID_COLUMN not in chunk.columns:
            raise ValueError(
                f"TS CSV is missing required column {TS_VOTER_ID_COLUMN!r}. "
                f"Got columns: {list(chunk.columns)[:10]}..."
            )

        records = []
        for i, row in enumerate(chunk.itertuples(index=False)):
            row_dict = row._asdict()
            voter_id = str(row_dict.get(TS_VOTER_ID_COLUMN, "")).strip()
            if not voter_id:
                # Skip rows with missing IDs; log but don't fail the file.
                logger.warning(
                    "Skipping row %d in %s: empty %s",
                    source_row_offset + i, source, TS_VOTER_ID_COLUMN,
                )
                continue
            records.append((
                voter_id,
                state,
                json.dumps(row_dict, default=str),
                source,
                int(source_row_offset + i),
                ingested_at,
            ))

        if not records:
            source_row_offset += len(chunk)
            continue

        df = spark.createDataFrame(records, schema=bronze_schema)
        df.write.format("delta").mode("append").save(bronze_path)
        total += df.count()
        source_row_offset += len(chunk)
        logger.info("Bronze append: %d rows (total: %d)", len(records), total)

    logger.info(
        "ingest_bronze complete: %s -> bronze.voter_file_ts (%d rows, state=%s)",
        source, total, state,
    )
    return total
