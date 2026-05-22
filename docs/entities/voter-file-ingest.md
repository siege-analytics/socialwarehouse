# Voter-file ingest

Generic contract for vendor voter-file importers. Each of PDI, L2, Catalist, TargetSmart implements this contract; the shared shape is captured here so the four vendor docs can focus on what's different.

Per [`docs/architecture.md`](../architecture.md): warehouse first, web app last. Importers populate the canonical Delta substrate (`silver.persons`, `silver.person_scores`, `silver.vote_history`); the PostGIS star schema is materialized from silver in a follow-on step.

## Pipeline shape

```
Vendor file (CSV / Parquet / API)
   │
   │ ingest_bronze()
   ▼
bronze.voter_file_<vendor>  (Delta; raw row as JSON string)
   │
   │ silver-build job (Spark)
   ▼
silver.persons + silver.person_scores + silver.vote_history  (Delta; canonical)
   │
   │ Spark -> PostGIS materialization (sub-issue B.4 of #250)
   ▼
DimPerson + FactPersonScore + FactVoteHistory  (PostGIS star schema)
```

## Bronze contract

Bronze is append-only. Each row stores the full vendor payload as a JSON string in the `raw` column, plus minimal extracted columns: `vendor_voter_id` (natural key), `state_abbreviation` (partition key), `source_file`, `source_row`, `ingested_at`.

Re-running the same file appends new rows tagged with new `ingested_at`. Bronze keeps full provenance; silver dedups.

## Silver contract

Silver is upsert-on-natural-key. Natural key: `(vendor, vendor_voter_id)`. Same physical voter loaded from two vendors yields TWO silver rows (cross-vendor matching is a follow-on; the schema permits it via a `canonical_person_id` column addition later).

Each importer:

1. Parses each bronze row's `raw` JSON.
2. Maps vendor fields to canonical column names (per the vendor's `mappings.py`).
3. Stashes unmapped vendor fields in `vendor_extras` (`Map<String,String>`).
4. Coerces types (string → date / float / int / bool per the canonical schema).
5. Upserts silver.persons on the natural key.

Scores and vote history are extracted into `silver.person_scores` and `silver.vote_history` by separate silver-build jobs (sub-issues B.2 / B.3 of #250). The thin spine ships persons only.

## Idempotency

- **Bronze**: appends. Re-running same file = duplicate bronze rows; provenance preserved.
- **Silver**: upserts on natural key. Re-running silver build = last-bronze-row-wins per natural key.
- **PostGIS materialization**: upserts on natural key. Re-running = same end state.

The full pipeline is idempotent end-to-end.

## Vendor-divergent fields

Each vendor ships fields the others don't. Canonical schema captures the common subset (per the TS-derived field-completeness checklist); vendor-divergent fields go in `vendor_extras` (silver, single map) and `<vendor>_extras` JSONField (PostGIS, per-vendor columns).

When a `vendor_extras` key becomes load-bearing — queried often, present across vendors, type-stable — promote it to a canonical column per [`docs/warehouse-schema-evolution.md`](../warehouse-schema-evolution.md).

## Vendor-specific runbooks

- TargetSmart: [`docs/electoral/targetsmart-importer.md`](../electoral/targetsmart-importer.md)
- L2, Catalist, PDI: sub-issues C-E of #250 (forthcoming).

## See also

- [`docs/architecture.md`](../architecture.md) — warehouse-first principle.
- [`docs/entities/dim-person.md`](dim-person.md) — canonical Person model.
- [`docs/entities/fact-person-score.md`](fact-person-score.md) — score vocabulary.
- [`docs/entities/fact-vote-history.md`](fact-vote-history.md) — vote-event semantics.
