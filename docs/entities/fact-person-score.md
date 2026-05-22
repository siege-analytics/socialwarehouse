# FactPersonScore

Per-person score events: partisan scores, turnout propensity, issue-stance models, anything vendors ship that is a numeric value attached to a voter.

## Tall format

One row per `(person, score_type, source_vendor, methodology_version)`. The `score_type` is a free string, not an enum. Adding a new score type is a new row, not a migration.

This is intentional: vendor scoring vocabularies grow every cycle (new issue-stance models, refreshed turnout models, etc.). A wide-format table with a column per score type would be a migration treadmill.

## Vendor scores are not interchangeable

A TS partisan score and an L2 partisan score are not the same number even when both are normalized to `[0, 1]`. Each carries its `source_vendor` and `methodology_version`. Querying "give me the partisan score for this person" requires picking a source explicitly:

```python
person.scores.filter(
    score_type="partisan_score",
    source_vendor="ts",
).latest("scored_at")
```

Don't average across vendors; don't pick "whichever vendor has the most recent." That silently introduces methodology mixing.

## Score-type vocabulary (registered)

Importers must use these strings for the listed concepts. Add new strings as new score types — but if a vendor's score maps cleanly to one of these, use the registered string, not a vendor-specific alias.

| `score_type` | Meaning | Range | Vendors known to ship |
|---|---|---|---|
| `partisan_score` | Probability the person votes D (or supports D); higher = more D | 0.0 – 1.0 | TS, L2, Catalist, PDI |
| `turnout_propensity_general` | Probability the person votes in a general | 0.0 – 1.0 | TS, L2, Catalist, PDI |
| `turnout_propensity_primary` | Probability the person votes in a primary | 0.0 – 1.0 | TS, L2, Catalist |
| `ideology_score` | Liberal-conservative axis; higher = more conservative | 0.0 – 1.0 | TS, L2 |
| `issue_<topic>` | Issue-specific stance (e.g. `issue_abortion`, `issue_climate`, `issue_gun_safety`) | 0.0 – 1.0 typical | TS, L2 (varies) |
| `engagement_score` | Likelihood of responding to outreach | 0.0 – 1.0 | TS, Catalist |
| `persuadability_score` | Likelihood of being moved by persuasion contact | 0.0 – 1.0 | TS |

Importers writing new score types should:

1. Check the registered list above; use the existing string if it fits.
2. Add the new string to this document AND to the importer's docstring.
3. Name the methodology version explicitly: cycle year + vendor revision (e.g. `2024Q4`).

## Methodology version semantics

`methodology_version` is a free string but should follow the pattern `<cycle><quarter>` or `<vendor>-<version>` so consumers can compare versions chronologically. Examples:

- `2024Q4`, `2026Q1` — for cycle-aligned refreshes
- `ts-v3.2`, `l2-2024.11` — for vendor-versioned refreshes
- `manual-2026-05-22` — for one-off bespoke scoring

The `unique_together = (person, score_type, source_vendor, methodology_version)` constraint means re-running an importer with the same methodology version is idempotent. Bumping the methodology version creates a parallel row; both are queryable.

## Schema evolution

`score_type` and `methodology_version` evolve freely (new strings, no migrations). The columns themselves are stable; if a fundamentally new score shape appears (e.g. multi-dimensional scores), file a follow-on sub-issue.

## See also

- [`docs/architecture.md`](../architecture.md) — warehouse-first principle.
- [`docs/entities/dim-person.md`](dim-person.md) — Person model.
- Refs: SW#250 (initiative), SW#251 (this sub-issue).
