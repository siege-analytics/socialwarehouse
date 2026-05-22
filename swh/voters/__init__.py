"""
Voter file loaders for SocialWarehouse.

Two paths exist:

- Legacy raw-PG-table loader (`swh.voters._legacy_raw`) — pre-#251 path that
  reads TargetSmart-format CSV directly into a PostGIS table. Still useful
  for ad-hoc analytical work where the medallion path is overkill. Public
  symbols re-exported here for back-compat.
- Medallion importers (`swh.voters.ts`, plus L2/Catalist/PDI follow-ons) —
  bronze ingest + silver canonical mapping into the warehouse star schema.
  This is the path the warehouse-first architecture targets; see
  `docs/architecture.md` and `docs/entities/voter-file-ingest.md`.
"""

from swh.voters._legacy_raw import (
    DEFAULT_COLUMNS,
    DEFAULT_CSV_ENCODING,
    TARGETSMART_DEFAULT_DTYPES,
    load_voter_file,
    voter_file_to_geodataframe,
)

__all__ = [
    "DEFAULT_COLUMNS",
    "DEFAULT_CSV_ENCODING",
    "TARGETSMART_DEFAULT_DTYPES",
    "load_voter_file",
    "voter_file_to_geodataframe",
]
