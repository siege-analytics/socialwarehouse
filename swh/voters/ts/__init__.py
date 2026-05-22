"""
TargetSmart voter-file importer (SW#257, sub-issue B of #250).

Thin spine: CSV -> bronze.voter_file_ts -> silver.persons. Score
extraction (B.2), vote-history extraction (B.3), and PostGIS
materialization (B.4) are follow-on sub-issues.

Public functions:

- `ingest_bronze(spark, csv_path, state)`: read TS-format CSV, append
  rows to `bronze.voter_file_ts` as JSON-stringified payloads.
- `build_silver_persons(spark)`: read bronze, map TS fields to canonical
  columns, upsert `silver.persons`.

See `swh.voters.ts.mappings` for the TS-to-canonical field mapping.
See `docs/electoral/targetsmart-importer.md` for the operator runbook.
"""

from swh.voters.ts.bronze import ingest_bronze
from swh.voters.ts.scores import extract_scores
from swh.voters.ts.silver import build_silver_persons
from swh.voters.ts.vote_history import compute_aggregates, extract_vote_history

__all__ = [
    "ingest_bronze",
    "build_silver_persons",
    "extract_scores",
    "extract_vote_history",
    "compute_aggregates",
]
