# F11 step 3: Address cached-GEOID consumer audit

**Date:** 2026-05-19
**Status:** Complete; no per-caller migration PRs needed.
**Closes:** F11 / SW#100 step 3 (per the v2 design's Q3 answer "mid-scope caller migration").

## Scope

After F11 step 2 (helpers, PR #187) and step 2b (signal-driven cache refresh, PR #203) landed, the `Address.{type}_geoid` cache is formally "current-by-construction" — every ABP write for a current vintage updates the cache transactionally. Step 3's job is the per-caller audit: are existing callers correct as-is, or do they need to migrate to the helpers (`boundary_on`, `boundary_history`, `boundary_timeline`)?

## Audit method

Grep for any access to `Address.{type}_geoid`:

```bash
$ rg -n '\b(addr|address|a)\.(state|county|tract|block_group|block|vtd|cd|sldl|sldu)_geoid\b' socialwarehouse/
```

Plus queryset filters on those fields:

```bash
$ rg -n 'filter\([^)]*\b(state|county|tract|block_group|block|vtd|cd|sldl|sldu)_geoid\b' socialwarehouse/
```

## Findings

### Writers (not consumers; out of step 3 scope)

| Site | Role |
|---|---|
| `socialwarehouse/geo/management/commands/assign_boundaries.py:367-374` | Writer: assigns boundaries → sets `addr.{type}_geoid` and saves. Already wrapped in `address_cache_refresh_disabled()` by step 2b (PR #203). |
| `socialwarehouse/geo/management/commands/geocode_addresses.py:158, 228` | Writer: sets `addr.geom = Point(...)`. Does not touch geoid cache fields. |

### Consumers (the only category step 3 cares about)

| Site | Pattern | Classification |
|---|---|---|
| `socialwarehouse/warehouse/services/geographic_enrichment.py:43` | `qs.filter(state_geoid=state_fips)` | **Needs current.** Cache is right. |
| `socialwarehouse/warehouse/services/geographic_enrichment.py:86` | `qs.filter(tract_geoid=tract_geoid).count()` | **Needs current.** Cache is right. |
| `socialwarehouse/warehouse/services/geographic_enrichment.py:122` | `qs.filter(state_geoid=state_fips)` | **Needs current.** Cache is right. |
| `socialwarehouse/warehouse/services/geographic_enrichment.py:138` | `qs.filter(tract_geoid=tract_geoid).count()` | **Needs current.** Cache is right. |

All four consumer sites are "addresses currently in this boundary" queries. Step 2b makes the cache correct for that semantic. **No migration needed.**

### Out-of-scope

| Site | Why |
|---|---|
| `socialwarehouse/delta/enrichment.py:26, 110, 119` | Spark SQL strings building joins from `siege_geo` tables; does not read `Address.{type}_geoid`. |
| `socialwarehouse/delta/tables.py:75-83, 120-129` | Delta-table schema field definitions; static. |
| `socialwarehouse/geo/models/address.py:127-141` | Field declarations on the model itself. |
| `socialwarehouse/geo/models/address_boundary.py:75-85` | ABP's own geoid columns; not Address-level cache reads. |
| `socialwarehouse/geo/migrations/*` | Migration files (historical). |
| `tests/**` | Test files exercising the model + the helpers. Test code is allowed to read the cache directly when validating it. |
| `vendor/geodjango_simple_template/**` | Vendored third-party code; not maintained here. |

## Decision

**Step 3 ships as a docstring update + this audit doc.** No per-caller code migrations needed:

- Every consumer site is "currently in this boundary" semantic. The cache is correct for that.
- Sites that need history (e.g., "did this address ever fall in CD-12?") would have used the helpers from day one — those callers haven't been written yet because the feature didn't exist before F11 step 2.

The F11 helpers (`boundary_on`, `boundary_history`, `boundary_timeline`, `geoid_on`, `current_geoid`, `current_boundaries`, `boundary_at`) remain the canonical surface for any *new* code that needs the as-of-date or historical-trace views.

## Docstring updates (in this PR)

`Address.current_boundaries()` and `Address.current_geoid(type)` had a caveat "until the F11 step-2b signal-driven cache refresh is in place." That caveat is now resolved — both methods are formally equivalent to reading the cache. Updated docstrings.

## Future work surfaced by the audit (filed separately)

- A coding-rule entry in the workspace skills tree saying "for new code that needs the *current* assignment, read the cache directly; for history or as-of-date, use the helpers." Promotes the discoverability gain from the helpers without forcing every caller through them. Filed via this audit's commit; no separate ticket.

## Follow-ups that were considered and rejected

- "Convert all `filter(geoid=...)` sites to use a manager method." Rejected: adds indirection without benefit; the direct filter is the idiomatic Django shape for "currently in this boundary."
- "Add a deprecation warning on direct `addr.{type}_geoid` access." Rejected: the cache is the canonical fast-path; deprecating it would be hostile to the dozen callers using it correctly.

## References

- F11 design v2: `docs/designs/f11-address-temporal-boundary-history.md`
- F11 step 2: PR #187 (merged)
- F11 step 2b: PR #203 (merged)
- F11 step 2b design: PR #197 (merged)
