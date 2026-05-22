# TargetSmart importer

Operator runbook for ingesting TargetSmart voter files through SocialWarehouse's medallion pipeline.

This is the thin spine: CSV → `bronze.voter_file_ts` → `silver.persons`. Score extraction, vote-history extraction, and PostGIS materialization are follow-ons (sub-issues B.2 / B.3 / B.4 of #250).

## Prerequisites

- SocialWarehouse deployed (PostGIS + Python + Spark).
- A TargetSmart voter-file CSV. Default file format is UTF-8 with BOM; the importer handles BOM via `utf-8-sig`.
- TARGETSMART_DEFAULT_DTYPES (in `swh.voters._legacy_raw`) is applied at read time to preserve leading-zero IDs (precinct codes, county FIPS, ZIP codes).

## Running the importer

```bash
swh ingest-voter-file \
  --vendor ts \
  --file /data/inputs/TX_voters.csv \
  --state TX
```

This runs both bronze + silver phases. Bronze appends rows to `bronze.voter_file_ts` partitioned by `state_abbreviation`; silver upserts canonical rows to `silver.persons`.

For staged loads (bronze only, defer silver):

```bash
swh ingest-voter-file --vendor ts --file ... --state TX --skip-silver
```

Then later:

```bash
python -c "
from socialwarehouse.delta.config import get_spark_session
from swh.voters.ts import build_silver_persons
spark = get_spark_session()
build_silver_persons(spark)
"
```

## What lands where

### Canonical columns on `silver.persons`

Mapped from TS via `swh/voters/ts/mappings.py`:

| Canonical | TS source | Notes |
|---|---|---|
| `vendor_voter_id` | `vb.voterbase_id` | Natural key together with `vendor='ts'` |
| `first_name`, `middle_name`, `last_name`, `name_suffix` | `vb.tsmart_*` | |
| `dob` | `vb.voterbase_dob` | |
| `gender`, `ethnicity` | `vb.voterbase_gender`, `vb.voterbase_race` | |
| `registration_status` | `vb.vf_voter_status` | active / inactive / purged / pending |
| `registration_state` | `vb.vf_source_state` | 2-char USPS; falls back to `--state` flag if blank |
| `registration_date` | `vb.vf_reg_cass_date` | |
| `party_registration` | `vb.vf_party` | D / R / U / etc. |
| `vendor_address_line1` ..`vendor_zip4` | `vb.vf_reg_*` | Vendor-supplied raw; audit |
| `latitude`, `longitude` | `vb.tsmart_latitude`, `vb.tsmart_longitude` | TS-geocoded |
| `cd_geoid`, `sldu_geoid`, `sldl_geoid`, `county_geoid`, `tract_geoid`, `block_group_geoid`, `zcta_geoid` | `vb.vf_cd`, `vb.vf_sd`, `vb.vf_hd`, `vb.tsmart_county_fips`, `vb.tsmart_tract_geoid`, `vb.tsmart_block_group_geoid`, `vb.vf_zcta_geoid` | TS pre-joined districts |
| `household_id`, `household_size`, `is_head_of_household` | `vb.tsmart_household_*` | |

### Unmapped TS columns → `vendor_extras`

Everything else (scores, segmentation flags, internal IDs, proprietary derived fields) goes into `vendor_extras` as a `Map<String,String>`. Keys retain the TS column name verbatim, including the `vb.` / `vb.tsmart_` prefix.

If a TS column starts getting queried often, promote it to a canonical column per [`docs/warehouse-schema-evolution.md`](../warehouse-schema-evolution.md).

### Explicitly excluded (PII)

`vb.voterbase_phone_wireless` is mapped to `None` in `TS_TO_CANONICAL` — neither canonical NOR `vendor_extras`. Operator opt-in is required to include it.

If you need additional PII fields included, edit `mappings.py` and file a follow-on PR with the justification.

## Idempotency

Re-running on the same file appends new bronze rows (provenance preserved) and re-upserts silver rows on the natural key. End-state is identical to a one-shot load.

## Out of scope (this importer)

- **Score extraction** (`silver.person_scores`): TS ships `vb.tsmart_partisan_score`, `vb.tsmart_*_propensity_*`, `vb.tsmart_*_score`, issue-stance scores, etc. These currently live in `vendor_extras` until B.2 of #250 ships.
- **Vote-history extraction** (`silver.vote_history`): TS ships `vb.vf_g_<year>` / `vb.vf_p_<year>` / `vb.vf_g_method_<year>` columns. These live in `vendor_extras` until B.3.
- **Address resolution** to `socialwarehouse.geo.Address`: silver.persons keeps the raw vendor address and lat/lon; the FK linkage backfills in B.4 via a Spark spatial join.
- **PostGIS materialization** (silver → DimPerson / FactPersonScore / FactVoteHistory): B.4.

## Troubleshooting

### `TS CSV is missing required column 'vb.voterbase_id'`

The importer hard-requires `vb.voterbase_id` as the natural key. If your TS export uses a different column for the voter id, either rename it in the CSV before ingest, or file a ticket — TS schema versions evolve and we may need to update the mapping.

### Empty `vendor_voter_id` warnings in logs

Some TS files contain rows with blank `vb.voterbase_id` (test rows, partial exports). The importer skips them and logs a warning per row. Check the log for the row offsets and decide whether the source CSV needs cleaning.

### `Could not find the GDAL library` error

This is unrelated — Django GIS startup failure. See the SW quickstart for GDAL setup; the TS importer itself doesn't touch GDAL until B.4's PostGIS materialization.

## See also

- [`docs/entities/voter-file-ingest.md`](../entities/voter-file-ingest.md) — generic importer contract.
- [`docs/entities/dim-person.md`](../entities/dim-person.md) — canonical Person model.
- [`docs/warehouse-schema-evolution.md`](../warehouse-schema-evolution.md) — promoting `vendor_extras` keys.
