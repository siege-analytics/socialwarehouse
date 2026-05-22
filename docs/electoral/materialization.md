# Electoral substrate materialization

Operator runbook for materializing the silver Delta substrate (silver.persons / silver.person_scores / silver.vote_history) into the PostGIS star schema (DimPerson / FactPersonScore / FactVoteHistory) that the Django web app reads.

This is the final link in the warehouse-first pipeline (per [`docs/architecture.md`](../architecture.md)). Until this runs, silver Delta has TS data but PostGIS doesn't, so Django views / admin can't surface anything.

## Prerequisites

- SocialWarehouse deployed (Postgres + Python + Spark).
- TS data already ingested through bronze + silver via [`docs/electoral/targetsmart-importer.md`](targetsmart-importer.md).
- Optionally: scores and vote-history extracted via `--include-scores` / `--include-vote-history`. Both are no-ops at materialize-time if silver tables are empty.

## Running the materializer

### All three tables in order

```bash
swh materialize-electoral all
```

This runs persons → scores → vote-history in dependency order. Scores and vote-history reference DimPerson by FK; running them without persons-first warn-and-skips on missing FK lookup rather than failing.

### Individual tables

```bash
swh materialize-electoral persons         # silver.persons -> DimPerson
swh materialize-electoral scores          # silver.person_scores -> FactPersonScore
swh materialize-electoral vote-history    # silver.vote_history -> FactVoteHistory
```

Use cases:
- After re-running TS importer on a new file: `persons` (then `scores` / `vote-history` if those silver tables were also updated).
- After a re-score-only run: `scores` alone.
- Debugging a single table.

## Idempotency

All three are idempotent. Re-running on identical silver yields identical PostGIS state.

Mechanism: Django ORM `bulk_create(update_conflicts=True, unique_fields=[...], update_fields=[...])` against the natural-key constraints declared in #251's migration:

- `DimPerson`: `(vendor, vendor_voter_id)`
- `FactPersonScore`: `(person, score_type, source_vendor, methodology_version)`
- `FactVoteHistory`: `(person, election_date, election_type, source_vendor)`

`update_fields` covers everything that can change between runs. `created_at` and `loaded_at` are excluded (preserve original timestamps).

## Order requirement

Persons MUST be materialized before scores or vote-history because of the FK constraint. The `all` subcommand enforces this; standalone subcommands print a warning + skip rows whose FK lookup misses:

```
materialize_scores: skipped 1234 rows because their DimPerson is not
materialized. Run materialize_persons first.
```

Re-running `materialize_persons` followed by `materialize_scores` resolves the skips on the next run (the persons land and the scores find their FKs).

## Vendor extras dispatch

`silver.persons.vendor_extras` is one Map<String,String> on the Delta side. PostGIS DimPerson has four `*_extras` JSONField columns. The materializer dispatches: rows with `vendor='ts'` → `ts_extras`; `vendor='l2'` → `l2_extras`; etc. Other vendor-extras fields default to `{}` on each row.

For unknown vendor strings, the materializer logs a warning and drops the extras (canonical fields still ship).

## Address resolution

DimPerson.address is a nullable FK to `sw_geo.address`. This materializer does NOT populate it; silver.persons.address_id is null after the TS importer (latitude/longitude are present but Address records are not linked).

Backfill is filed as sub-issue B.5 of #250 — a separate Spark spatial-join job from silver.persons.lat/lon → silver.addresses → DimPerson.address.

Until B.5 ships, the web app surfaces work on the boundary-cache GEOID columns directly on DimPerson (cd_geoid, sldu_geoid, etc.) without going through geo.Address.

## Troubleshooting

### `materialize_scores: skipped N rows`

DimPerson for those rows isn't materialized yet. Run `materialize-electoral persons` first, then re-run scores.

### `unknown vendor 'xyz' for vendor_voter_id=...`

A silver.persons row has a vendor value not in `{pdi, l2, catalist, ts}`. Canonical fields still materialize; extras are dropped. Verify the silver-build job set `vendor` correctly.

### `IntegrityError on bulk_create`

Should not happen given the `update_conflicts=True` shape. If it does, check that the natural-key unique constraints on the PostGIS migration match the `unique_fields` arg in the materializer (`#251`'s migration is the source of truth).

## See also

- [`docs/architecture.md`](../architecture.md) — warehouse-first / web-app-last principle.
- [`docs/entities/dim-person.md`](../entities/dim-person.md) — canonical Person model + vendor mapping.
- [`docs/entities/voter-file-ingest.md`](../entities/voter-file-ingest.md) — full pipeline contract.
- Refs: SW#261 (this), SW#250 (initiative), SW#251 (substrate).
