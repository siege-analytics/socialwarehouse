# FactVoteHistory

Per-person per-election vote events. The truth-of-record for who voted when and how, sourced from voter file vote history sections.

## Natural key

`unique_together = (person, election_date, election_type, source_vendor)`.

The inclusion of `source_vendor` means two vendors reporting the same vote both land in the table — neither is masked. Cross-vendor reconciliation (when two vendors disagree on `voted_method`) is a consumer-side decision; the data preserves both observations.

## Election types

| `election_type` | Meaning |
|---|---|
| `general` | November general election (federal + state) |
| `primary` | Party primary (open or closed) |
| `runoff` | Runoff following a non-decisive election |
| `special` | Special election (mid-cycle, single-office) |
| `local` | Municipal / school board / non-partisan local |
| `other` | Anything that doesn't fit the above |

`other` should be rare; if a vendor consistently ships an election type not in this list, file a sub-issue to add it.

## Voted methods

| `voted_method` | Meaning |
|---|---|
| `in_person` | In-person on election day |
| `absentee` | Absentee ballot (excuse-required) |
| `mail` | Vote-by-mail / no-excuse absentee |
| `early` | Early in-person |
| `provisional` | Provisional ballot (resolution status not tracked here) |
| `unknown` | Vendor did not report the method |

Default is `unknown`. Importers that have method data must populate it.

## Aggregate denormalization

`DimPerson.general_election_count`, `primary_election_count`, `total_vote_count`, `last_voted_at`, and `vote_frequency_category` are computed FROM this table by the silver-build Spark job and materialized onto DimPerson for query speed.

If a consumer query needs sub-ingest-cadence aggregates (e.g. mid-load partial counts), query FactVoteHistory directly with `aggregate(Count('id'))`. Don't rely on DimPerson's denormalized values mid-load.

## Cross-vendor disagreement

When two vendors report the same vote with different `voted_method`:

- Both rows are preserved (`unique_together` includes `source_vendor`).
- DimPerson aggregates count the vote once per `(election_date, election_type)` to avoid double-counting. The Spark job handles this; see the silver-build doc when it ships.
- Consumer queries that want "give me this person's method" must pick a vendor; querying across both without picking is ambiguous.

## TargetSmart importer mapping (SW#260)

Defined in `swh/voters/ts/vote_history_mappings.py`. TS encodes vote participation as per-cycle columns; the importer parses each column name into `(election_type, year, is_method_column)`.

### Column patterns

| TS prefix | Election type | Default election date |
|---|---|---|
| `vb.vf_g_<year>` | general | `<year>-11-05` |
| `vb.vf_p_<year>` | primary | `<year>-03-15` |
| `vb.vf_g_method_<year>` | general (method) | (paired with `vb.vf_g_<year>`) |
| `vb.vf_p_method_<year>` | primary (method) | (paired with `vb.vf_p_<year>`) |

A row is emitted to `silver.vote_history` when the participation column is truthy (`Y`, `y`, `1`, `T`, `t`, `TRUE`, `True`). Method columns supply `voted_method`; if absent, `voted_method` defaults to `unknown`.

### Method codes

| TS code | Canonical `voted_method` |
|---|---|
| `I` | `in_person` |
| `A` | `absentee` |
| `M` | `mail` |
| `E` | `early` |
| `P` | `provisional` |
| (empty / unknown) | `unknown` |

### Vote-frequency buckets

Computed in `compute_aggregates()` and materialized onto `silver.persons.vote_frequency_category`:

| Bucket | Definition |
|---|---|
| `super_voter` | ≥4 generals voted |
| `regular` | 2-3 generals voted |
| `occasional` | exactly 1 general voted |
| `non` | 0 generals voted (regardless of primary participation) |

Operators with state-specific primary dates should extend `ELECTION_TYPE_PREFIXES` in `vote_history_mappings.py`; the defaults are documented approximations.

## Why we don't store more election metadata

`FactElectionResult` (existing) holds vote tallies, candidates, offices, parties at the geography level. `FactVoteHistory` is the per-person counterpart: "did this person vote?", not "what did they vote for?" (voter privacy means the latter is not in the file at all).

The two facts are joinable via `(election_date)` if a consumer needs to ask "of the people who voted in this election, what was the overall result?" — but that's a join, not a denormalization.

## See also

- [`docs/architecture.md`](../architecture.md) — warehouse-first principle.
- [`docs/entities/dim-person.md`](dim-person.md) — Person model + aggregate refresh cadence.
- Refs: SW#250 (initiative), SW#251 (this sub-issue).
