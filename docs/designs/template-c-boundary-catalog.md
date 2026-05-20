# Template-readiness C / SW#191 — Boundary catalog expansion (design)

**Status:** Design v1. Awaiting maintainer answers on the four open questions.

**Parent:** SW#189 (template-readiness initiative).
**Blocked by:** B (#190) — done after PR #206.
**Blocks (partially):** D (#192 demographic ingest needs `place` and `puma`), E (#193 economic needs `zcta` and `cbsa`), F (#194 civic needs `school_district` and `special_district`).

## Goal

Expand the boundary catalog from today's nine types (`state`, `county`, `tract`, `block_group`, `block`, `vtd`, `cd`, `sldl`, `sldu`) to cover the boundary types each of the four data domains keys on:

| New type | Used by | Source | Priority |
|---|---|---|---|
| `zcta` | Economic (IRS SOI, FCC broadband, commercial), some demographic | Census ZCTAs (5-digit) | high (E needs it) |
| `place` | Demographic (city-level), civic | Census Places (CDP / incorporated) | high (D needs it) |
| `cbsa` | Economic (BLS / BEA standard) | Census/OMB CBSA delineation | high (E needs it) |
| `school_district` (unified / elementary / secondary) | Civic, demographic (school-age) | Census + NCES | high (F needs it) |
| `puma` | Demographic (ACS public-use microdata) | Census PUMAs | medium (D Phase 2) |
| `special_district` (with subtype: fire / water / hospital / library / cemetery) | Civic | Census Special Districts | medium (F Phase 2) |
| `urban_area` / `urban_cluster` | Demographic, civic | Census UA delineation | low (nice-to-have) |

## What lands per new type

For each new boundary type, the implementation adds:

1. **siege_utilities model.** The boundary geometry + attributes table (vintage-aware via Vintage FK). This is upstream work — file a SU ticket per type or batched.
2. **SW Address-cache field.** `Address.{type}_geoid` CharField (length matching the GEOID format for the type).
3. **SW ABP column.** `AddressBoundaryPeriod.{type}_geoid` CharField.
4. **`Address._BOUNDARY_TYPES` tuple entry.** So F11 helpers cover the new type automatically.
5. **Migration.** AddField on Address + ABP (+ index if needed).
6. **Test.** Covers F11 helper integration (`boundary_history(type="zcta")`, `boundary_on("zcta", date)`, etc.).
7. **Entity doc.** One markdown file per type at `docs/entities/boundary_<type>.md`.

The per-type work is mechanical once one is done. We can ship the first as a worked example, then bulk the rest.

## Four open questions for the maintainer

### Q1. One PR per type, or batched?

Three options:
- (a) **One PR per boundary type.** Seven small PRs. Each is reviewable in isolation; per-type problems don't block sibling work.
- (b) **One PR for the high-priority subset** (zcta, place, cbsa, school_district), then a second PR for the medium/low subset (puma, special_district, urban_area).
- (c) **One PR for all seven types.** Big PR; single review pass; all-or-nothing.

**Recommendation: (b).** The high-priority subset (4 types) is what unblocks D/E/F's first phases. The medium subset can wait for those ingest packages to actually need them.

### Q2. Sub-typing for `special_district`?

Census Special Districts come in many kinds (fire protection, water, hospital, library, cemetery, mosquito abatement, etc.). Two options:

- (a) **One `special_district` boundary type with a `kind` CharField on the model** (`special_district_kind: fire | water | hospital | ...`). Single FK target; queries can filter by kind. Each `Address.special_district_geoid` cache is single-valued — but addresses are often in MULTIPLE special districts (a fire AND a water district both cover most addresses). The single-cache shape would only hold one; the helper would return all via `boundary_history("special_district")`.
- (b) **One boundary type per kind** (`Address.fire_district_geoid`, `Address.water_district_geoid`, ...). Each is its own cache field. More columns on Address.

Recommendation: **(a)** with the helper carrying the multi-row return shape. The cache holds the "most recent special-district assignment" which is operationally fuzzy, but the helper is the authoritative path for "all special districts this address is in." Document the asymmetry.

### Q3. ZCTA cache as the only ZIP-like field?

Today Addresses already have `zip5` (the postal ZIP code as written on the envelope). ZCTA is the Census-derived approximation of a 5-digit ZIP for geographic analysis — usually equal to `zip5` but not always (PO boxes, military APO, edge cases). Two options:

- (a) **Add `zcta_geoid` separately from `zip5`.** Clean; the cache field is Census-derived and stable.
- (b) **Reuse `zip5` as the ZCTA cache.** Simpler. Loses the postal-vs-geographic distinction.

Recommendation: **(a) separate field.** The distinction matters for economic ingest (IRS SOI is ZCTA-keyed, not postal-ZIP-keyed) and the data-quality story is cleaner when the postal ZIP and Census-derived ZCTA can diverge per-row.

### Q4. Vintage shape per new type?

Most new types use the existing `census-decadal` Vintage (state, county, ZCTA, place, school district, special district — all per-decade). PUMAs are also census-decadal (revised each decade). CBSAs are OMB-published with their own cadence (~every few years). Two options:

- (a) **All new types use `census-decadal` vintage** uniformly. CBSAs get a slight mismatch but are usable.
- (b) **Add a `cbsa-omb` vintage kind** to the polymorphic Vintage for the OMB cadence. Faithful to source semantics; one more kind to maintain.

Recommendation: **(a)** for this PR; **(b)** as a follow-up if CBSAs prove operationally awkward against decadal vintages. Adding a vintage kind later is a one-row addition to KIND_CHOICES + a subclass + migration; not blocking.

## What this PR delivers

Just the design note. Maintainer answers Q1-Q4; implementation PR(s) follow per the chosen sequencing.

## Sequencing

- This PR (design v1) → maintainer Q1-Q4 answers.
- Per-type implementation PRs in the chosen batching (Q1's answer).
- Each type unblocks the matching ingest sub-issue's specific phase (e.g., ZCTA → E Phase 2 IRS SOI; place → D Phase 2 city-level demographic).

## References

- Parent: SW#189
- B PR #2 (just merged): #206 (polymorphic Vintage cutover; foundation for Vintage FKs on new boundary types)
- Existing boundary types live in siege_utilities at `siege_utilities/geo/django/models/boundaries.py`
- Existing `Address._BOUNDARY_TYPES` at `socialwarehouse/geo/models/address.py:337-340`
