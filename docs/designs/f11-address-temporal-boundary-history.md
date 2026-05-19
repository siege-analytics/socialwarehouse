# Think note: F11 / SW#100 — Address belongs to *which* boundary set, *when*?

## What the user actually said

> "This all needs to change. Census Year was the original plan, Vintage became important later, but as we are seeing more and more insane redistrictings happen, there are multiple plans that can happen in a year, even. We need to know to which set of boundaries the address belonged to at any point."

This is **not** the "pick IntegerField vs FK" question I framed in the earlier triage. It's an architectural reframe: an Address's boundary membership is **temporal and plan-specific**, not a single attribute.

## Goal

Given an Address and a date, answer: which CD / state-leg-lower / state-leg-upper / VTD / county / tract / etc. did this address belong to **on that date** — accounting for:
- Multiple redistricting plans active in the same calendar year (court-ordered mid-cycle redraws are now routine).
- Plans that get struck down and replaced.
- Census vintage drift (TIGER 2020 vs TIGER 2010 boundaries).
- Plans that span less than a full year (Alabama 2022 — original CD plan, then court-ordered redraw, then again).

## What exists today

- `Address.census_year` — `IntegerField(default=2020)`. Single integer; can't represent two plans in the same year.
- `Address.{state,county,tract,block_group,block,vtd,cd,sldl,sldu}_geoid` — single string each; reflects one assignment.
- `Address.census_units_assigned_at` — DateTimeField; when the assignment was computed, not which date the assignment is valid for.
- `CensusVintageConfig` — has `decade`, `effective_start`, `effective_end`. Maps calendar year → vintage decade. Not plan-aware.
- `AddressBoundaryPeriod` — exists! FKs to `address`, `vintage` (CensusVintageConfig), `redistricting_plan` (siege_utilities). Has `state_geoid`, `county_geoid`, `tract_geoid`, `vtd_geoid`, `cd_geoid`, `sldl_geoid`, `sldu_geoid`, `assignment_method`, `context_date`. **This is the temporal history table already.** The `assign_boundaries` command writes to it. So the bones are in place — the questions are about how to USE it correctly and what to do with the Address-level cached fields.
- `siege_utilities.geo.django.models.RedistrictingPlan` — has effective dates, plan name, jurisdiction.

## Design options

### A. Promote AddressBoundaryPeriod to the canonical surface. Demote Address GEOID fields to "cached current assignment" or remove them.

**Reads**: any "what CD does this address belong to on date D?" query goes through `AddressBoundaryPeriod` filtered by date. Joins via the RedistrictingPlan to find the active plan for D, then reads the period's geoid for that plan.

**Address-level GEOID fields**: either
- (A1) Keep them as a cached convenience for "the current assignment under the latest plan in the latest vintage" — a denormalized read shortcut. Documented as denormalized; refreshed by the assign_boundaries command. Callers wanting historical-correct answers go through ABP.
- (A2) Remove them. Force every consumer through ABP. Cleaner but breaks every existing query that does `Address.objects.filter(cd_geoid="0628")`.

**`census_year`** on Address: keep as the cached current-vintage (still useful for "filter addresses by 2020-vintage assignments"); or drop in favor of joining through ABP → vintage.

### B. Keep Address GEOID fields as canonical. Use AddressBoundaryPeriod only as an audit log.

Existing queries keep working. ABP records the history for replay but isn't load-bearing for any read. Loses much of the point — answers to "what did this address belong to on 2023-08-15?" stay inaccurate when there's been a mid-cycle redraw.

### C. Add an explicit date-parameterized query helper on Address.

`Address.geoids_as_of(date) -> dict` that reads ABP. Address fields stay as "current under latest plan" cache. Cheaper than A's full rearchitecture; preserves caller compatibility; gives the date-aware answer when callers need it.

## My read

**A1 + a date-parameterized helper** is the right end state. Reasons:
- ABP already exists and is being written by `assign_boundaries`. Reads should go through it for historical correctness.
- Removing the Address-level GEOID fields entirely (A2) breaks too many existing query sites without a transition plan. A1's denormalized-cache framing is honest and preserves caller compatibility.
- A C-only approach (B + helper) leaves the Address fields as the canonical surface, which is the framing that fails when multiple plans land in the same year.

## What this needs from you before I write code

1. **Confirm direction**: A1 (canonical ABP + denormalized cache on Address) vs B vs C. Or a hybrid I haven't named.
2. **Migration path**: keeping Address.{cd,sldl,...}_geoid means they need a clear refresh policy. Option: a Django signal on ABP write that updates Address.* to the latest-active-plan's geoid. Option: explicit refresh in `assign_boundaries`. Option: just document that they're stale-by-design and callers wanting current must query.
3. **Are existing `Address.cd_geoid` filter sites callers I should audit + migrate?** A quick grep tells me how big the surface is.
4. **What's the canonical "current" definition?** "The plan whose effective range contains today's date" OR "the plan that was active when last ran assign_boundaries" OR "the most recent plan by court date." Each yields a different denormalized cache.

## Sequencing

This is a substantial rearchitecture. I propose:

- **Step 1 (this PR)**: design note + your sign-off. No code.
- **Step 2**: helper method `Address.geoids_as_of(date)` and `Address.geoids_for_plan(plan)` that read ABP. Backward-compatible.
- **Step 3**: update key callers (geocode_addresses, assign_boundaries, geographic_enrichment) to use the helpers where date-awareness matters.
- **Step 4** (deferred): consider dropping or further demoting the Address-level GEOID fields once callers have migrated. May not happen if the cached fields stay useful.

No code until you've signed off on direction.

## Tickets this displaces / supersedes

- **F11 / SW#100** — the original "dual source of truth" framing is too small. Reframed to this.
- **F6 / SW#95 callable-default deferred path** — still deferred. The `DEFAULT_CENSUS_YEAR = 2020` constant approach I shipped for F6 is the right minimal move; the bigger story is this temporal rearchitecture.

## Risk

This affects the central model of the warehouse. A miscut on the design here is expensive. Hence the design-note-first discipline.
