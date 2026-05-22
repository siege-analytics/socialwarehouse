# DimPerson

Canonical voter dimension in the PostGIS star schema. The Django ORM-facing projection of the Delta `silver.persons` table.

## Position in the warehouse

```
Vendor file (PDI / L2 / Catalist / TS)
    ↓
bronze.voter_file_<vendor>  (Delta; raw row as JSON string)
    ↓ silver-build Spark job
silver.persons              (Delta; canonical, typed, vendor-neutral)
    ↓ Spark→PostGIS materialization
DimPerson                   (PostGIS; this model)
    ↓ Django ORM
Web app, admin, DRF API
```

Per [`docs/architecture.md`](../architecture.md): warehouse first, web app last. Silver is canonical; DimPerson is the serving-tier projection.

## Natural key

`(vendor, vendor_voter_id)` — `unique_together`.

Same physical voter loaded from two vendors yields TWO DimPerson rows. Cross-vendor probabilistic matching is a follow-on sub-issue of #250; the schema permits the addition of a `canonical_person_id` column linking the rows when the matcher ships.

## Current-only, not SCD2

Vendor voter files are themselves point-in-time snapshots. The effective-dated semantics that `DimGeography` uses (SCD Type 2) do not apply: a vendor doesn't ship "this voter was at this address from 2022-01-01 to 2024-03-15"; it ships "as of the file's load date, here's the voter."

Historical truth lives in `silver.persons` (append/upsert), where each load preserves the prior state. DimPerson is always the latest snapshot. Promote to SCD2 only if a concrete consumer asks for effective-dated person history and accepts the maintenance cost.

## Vendor mapping checklist

When implementing an importer (sub-issues B-E of #250), map each TS-equivalent vendor field to the canonical DimPerson column. Fields that don't map go in the `<vendor>_extras` JSONField.

| Canonical column | TS field | L2 field | Catalist field | PDI field |
|---|---|---|---|---|
| `vendor_voter_id` | `vb.voterbase_id` | `LALVOTERID` | `dwid` | `pdi_id` |
| `first_name` | `vb.tsmart_first_name` | `Voters_FirstName` | `first_name` | `first_name` |
| `last_name` | `vb.tsmart_last_name` | `Voters_LastName` | `last_name` | `last_name` |
| `dob` | `vb.voterbase_dob` | `Voters_BirthDate` | `birthdate` | `dob` |
| `registration_status` | `vb.vf_voter_status` | `Voters_Active` | `registration_status` | `voter_status` |
| `registration_state` | `vb.vf_source_state` | `Voters_StateVoterID` first 2 | `state` | `state` |
| `party_registration` | `vb.vf_party` | `Parties_Description` | `party_affiliation` | `party` |
| `address_line1` | `vb.vf_reg_address_1` | `Residence_Addresses_AddressLine` | `residence_street` | `address_line_1` |
| `city` | `vb.vf_reg_city` | `Residence_Addresses_City` | `residence_city` | `city` |
| `zip5` | `vb.vf_reg_zip` | `Residence_Addresses_Zip` | `residence_zip` | `zip` |
| `latitude` | `vb.tsmart_latitude` | `Residence_Addresses_Latitude` | `latitude` | `latitude` |
| `longitude` | `vb.tsmart_longitude` | `Residence_Addresses_Longitude` | `longitude` | `longitude` |
| `cd_geoid` | `vb.vf_cd` | `US_Congressional_District` | `cd` | `congressional_district` |
| `sldu_geoid` | `vb.vf_sd` | `State_Senate_District` | `sd` | `state_senate` |
| `sldl_geoid` | `vb.vf_hd` | `State_House_District` | `hd` | `state_house` |
| `household_id` | `vb.tsmart_household_id` | `Household_Composition` | `household_id` | `household_id` |
| `general_election_count` | `vb.vf_g_*` aggregated | `General_<year>` aggregated | `general_voted_*` aggregated | `general_*` aggregated |

This is a starter map; importer PRs (B-E of #250) fill in the rest. Unmapped vendor fields go in `<vendor>_extras`.

## Schema evolution

If a vendor extra becomes load-bearing — queried often, present across vendors, type-stable — promote it to a canonical column via [`docs/warehouse-schema-evolution.md`](../warehouse-schema-evolution.md).

## Aggregate refresh cadence

`general_election_count`, `primary_election_count`, `total_vote_count`, `last_voted_at`, `vote_frequency_category` are denormalized for query speed. They are computed by the silver-build Spark job from `silver.vote_history` and materialized onto DimPerson via the same Spark→PostGIS path.

The cadence is "per ingest run." Django signals are NOT used; signal-driven refresh would couple too tightly to ingest order in a bulk-load context. If a consumer needs sub-ingest-cadence aggregates, query `FactVoteHistory` directly.

## See also

- [`docs/architecture.md`](../architecture.md) — warehouse-first principle.
- [`docs/entities/fact-person-score.md`](fact-person-score.md) — score vocabulary.
- [`docs/entities/fact-vote-history.md`](fact-vote-history.md) — vote-event semantics.
- [`docs/warehouse-schema-evolution.md`](../warehouse-schema-evolution.md) — promotion playbook.
- Refs: SW#250 (initiative), SW#251 (this sub-issue).
