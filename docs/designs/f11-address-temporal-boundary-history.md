# Think note: F11 / SW#100 — Address belongs to *which* boundary set, *when*?

**Status:** Design v2. The four open questions from v1 are now answered by the maintainer (2026-05-19); the load-bearing user-facing feature is named explicitly. Ready for the step-2 implementation PR (helper methods on Address).

## The load-bearing feature (v2 framing, named explicitly)

> "There are addresses, and we'd be able to surface not only which boundaries it's currently contained by, but which ones it's ever been contained by."

This is the feature ABP exists to enable, and the one that justifies the temporal-history rearchitecture. Two views on the same Address:

- **Current view**: a flat readout of the boundaries this address is in **right now**. One row per boundary type (CD, state-senate, state-house, VTD, county, tract, ...). Cheap.
- **History view**: every boundary this address has *ever* been inside, with date ranges. A timeline.

The history view is the load-bearing one. The current view is the cheap one. Questions like "did this voter ever live in CD-12?" can only be answered by the history view; the current view literally cannot answer that. The implementation must serve both with the same data model — there is no separate "history table" added; `AddressBoundaryPeriod` already is that table.

## Resolved decisions (v2, 2026-05-19)

| Q | Answer | Why |
|---|---|---|
| 1. Direction | **A1 + helper.** ABP is the source of truth for both views; `Address.{cd,sldl,...}_geoid` becomes a cache of the *current* snapshot. | Removing the Address-level fields (A2) breaks every caller; B leaves the framing that fails when two plans land in the same year. A1 keeps callers compatible and gives the helper authoritative reads. |
| 2. Refresh policy for the denormalized cache | **(a) Signal-driven.** Every ABP write that lands a new current-period for an address updates the Address-level cached GEOIDs in the same transaction. | Any caller doing `Address.objects.filter(cd_geoid="06-12")` is implicitly asking "currently in CD 06-12." If the cache lags, that filter silently returns stale results. Pay the write-amplification once, at the write site, where ABP already knows it's superseding the previous period. (b) and (c) push staleness onto every caller and the cache stops being a cache. |
| 3. Caller audit scope | **Mid.** Warehouse enrichment, the geocode pipeline, and analytics queries that filter/group by Address-level GEOID. Each needs a one-line decision: "current-as-cached (use the field) or history / as-of-date (use the helper)." Most stay on the cache. | The cache is fine for the common case once (a) is in place. The few callers that need history opt into the helper. |
| 4. Canonical "current" definition | **(a) active-by-date(today).** Once the signal-driven refresh (Q2-a) is in place, the cache *is* "active-by-date(today)" by construction; the two definitions collapse into the same answer. | The legal/paranoid alternatives ((b) last-run, (c) most-recent-by-court-date) are real edge cases — what if `assign_boundaries` hasn't been re-run since the new plan took effect? — but they belong in a follow-up sub-feature, not in this PR. Filed as a future ticket. |

## Proposed helper API shape (step-2 PR)

```python
# Read methods on Address (model methods, not managers):

address.boundary_history(boundary_type=None)
    # All ABP rows for this address, optionally filtered to one boundary type.
    # Returns a queryset of AddressBoundaryPeriod ordered by effective_from desc.
    # The "ever been contained by" view.

address.boundaries_on(date)
    # The boundaries this address was in on the given date.
    # Returns dict { "cd": ABP-row, "sldl": ABP-row, ... } — one row per
    # boundary type whose effective range contains `date`. Missing keys mean
    # no ABP row covers `date` for that type.

address.current_boundaries()
    # Sugar for boundaries_on(date.today()).
    # NOTE: With Q2-a's signal-driven cache refresh, the result is equivalent
    # to reading address.cd_geoid / .sldl_geoid / ... directly. Use the cache
    # for hot-path filters; use this helper when you want the ABP row's
    # metadata (effective range, plan, assignment_method).
```

The helper lives on `Address` so callers do `address.boundary_history()` rather than threading the address through a free function. ABP-side query methods (`AddressBoundaryPeriod.objects.for_address_on_date(...)`) are fine to add as a sibling surface, but the model-method form is the documented public API.

### Addendum (2026-05-19): single-boundary + positional sugar

After the v2 helper API was named, the maintainer surfaced three more query shapes the audience asks for: "CD on date X", "in reverse chron, the N-th CD for this address", and "in reverse chron, CDs N through M for this address." Two sugar methods cover the first two; the third is the underlying queryset's native slicing, kept on the queryset to avoid API bloat.

```python
address.boundary_on(boundary_type, on_date)
    # Single ABP row for one boundary type as of on_date, or None.
    # Sugar for `boundaries_on(on_date).get(boundary_type)`.

address.boundary_at(boundary_type, position)
    # ABP row at `position` in reverse-chron history for the type.
    # 0-indexed. position=0 is the most recent. Returns None for
    # out-of-range rather than raising IndexError.

# For ranges, use the underlying queryset directly — no separate sugar:
address.boundary_history(boundary_type="cd")[2:8]
```

Audience note: the 0-indexed semantics is a deliberate API choice. A 1-based form would be more readable for non-technical end users, but the audience here is data analysts who expect Python/SQL conventions. Encoding 1-based would build a "is 5 the 5th or the 6th?" trap into the API at every call site. The queryset slice shape is the canonical range form for the same reason — analysts already know how Python slicing works.

### Addendum (2026-05-19, v2.2): timeline + geoid sugar after dogfooding

After step-2 + the v2.1 sugar shipped, dogfooding the API surfaced three gaps:

1. **The "ever been contained by" pitch is most useful as a timeline** — `[(geoid, effective_from, effective_to, plan_name), ...]` chronologically — and assembling it from raw ABP rows requires walking into `redistricting_plan.effective_from / effective_to` (or falling back to vintage-derived dates for NULL-plan rows). Every caller would write that loop five different ways. It belongs in the helper layer.
2. **Two-step geoid access is awkward.** `addr.boundary_on("cd", date).cd_geoid` reads weirdly and explodes if the row was None. A one-step `geoid_on(boundary_type, date)` returning the string (or None) closes the common case.
3. **A `current_geoid(boundary_type)` sibling** completes the symmetry with `current_boundaries`.

Authorized methods added in this addendum:

```python
address.boundary_timeline(boundary_type)
    # Chronological timeline. Returns list of BoundaryTimelineEntry
    # namedtuples (geoid, effective_from, effective_to, plan_name,
    # abp), sorted oldest-first.
    #
    # Effective ranges:
    #   - Plan-bound rows: from redistricting_plan.effective_from /
    #     effective_to (effective_to may be None for "still active").
    #   - NULL-plan rows: from vintage.effective_start /
    #     effective_end (converted to date(year, 1, 1) and
    #     date(year, 12, 31)).
    #
    # Adjacent same-geoid rows are NOT collapsed; callers wanting
    # that can itertools.groupby on the result. Collapse semantics
    # are opinionated (across vintage boundaries? plan-name-aware?)
    # and forcing them here would mis-shape the layered API.

address.geoid_on(boundary_type, on_date)
    # String GEOID (or None) for one boundary type as of on_date.
    # Sugar for `boundary_on(...).{type}_geoid` with None-safety.

address.current_geoid(boundary_type)
    # String GEOID (or None) for one boundary type as of today.
    # Sugar for `geoid_on(boundary_type, today)`. With the step-2b
    # signal in place, returns the same value as self.{type}_geoid.
```

Surface check: this brings the total to **seven public read methods** on Address — at the upper edge of "small API." Each method maps to a distinct caller-facing question (history, all-types-at-date, one-type-at-date, Nth-in-chron, current-all, current-one, timeline); bundling would lose the named-use-case discoverability that was the whole point. Hold at seven; revisit if an eighth is proposed.

Documentation amendments to existing methods (shipped alongside):
- `boundary_history()` unfiltered returns rows with sparse geoid fills (plan-bound CD rows have null sldl/sldu, etc.); docstring will name this.
- `current_boundaries()` / `current_geoid()` use `timezone.localdate()`; docstring notes that the answer is server-timezone-dependent at midnight boundaries.
- `boundary_history()` NULL `context_date` rows sort last under DESC (Postgres default); docstring notes this.

Deferred to follow-up ticket (does NOT block this step):
- **Perf: `boundaries_on(date)` always fetches all periods for the vintage**, even when called from `boundary_on(boundary_type, date)` for a single type. Single-digit-to-dozens of ABP rows per address is the realistic scale, so this is acceptable today. Worth filing in case `assign_boundaries` cadence grows.

## Sequencing (unchanged from v1, refined)

- **Step 1** (this PR, design v2): sign-off on the resolved decisions above. No code. **← this is where we are.**
- **Step 2**: implementation PR — helper methods on `Address` (`boundary_history`, `boundaries_on`, `current_boundaries`), additive only. Includes unit tests against a small ABP fixture. **Does NOT include the signal-driven cache refresh from Q2-a yet** — that's step 2b.
- **Step 2b**: separate PR for the Q2-a signal-driven refresh of the Address-level cached GEOIDs on ABP write. Includes the audit of existing ABP write sites so the signal is consistent. Sequenced after step 2 so the helper is the authoritative read path *before* the cache becomes formally "current-by-construction."
- **Step 3**: caller-migration PR(s) — the audit from Q3. Most callers stay on the cache; the few that need history adopt the helper. Per-caller or grouped by subsystem, depending on scope.
- **Step 4** (deferred, may not happen): consider further demoting or removing the Address-level GEOID fields once steps 2b + 3 are landed. Probably not — the cache stays useful indefinitely. Closed as won't-fix once steps 2-3 are stable.

## Follow-ups (filed separately, do not block this PR)

- **Edge-case: cache vs court-date drift.** If `assign_boundaries` hasn't run for a new plan that has legally taken effect, the cache is the "last-run" answer, not the "court-effective" answer. Today's Q4-a answer is "active-by-date(today)" under the assumption that ABP is up-to-date. The paranoid path (Q4-c: most-recent-by-court-date) is the safety net for that gap. Worth a ticket so it's not lost.

## Revision history

- **v1 (initial):** reframed F11 from "IntegerField vs FK" to "Address belongs to *which* boundary set, *when*?" Surfaced that ABP already exists as the temporal-history table. Proposed A1 + helper. Four open questions for the maintainer.
- **v2 (2026-05-19, after maintainer answers):** named the load-bearing user-facing feature ("not only which boundaries it's currently contained by, but which ones it's ever been contained by"). Resolved decisions table. Helper API shape spelled out. Sequencing split step 2 into step 2 (helper, additive) + step 2b (signal-driven refresh) so the helper lands as the authoritative read path before the cache becomes formally "current-by-construction." Unblocks step 2.
- **v2.1 (2026-05-19, addendum after step 2 opened):** added `boundary_on(type, date)` and `boundary_at(type, position)` sugar to cover three more named query shapes (single-type-as-of-date, positional). Range queries stay on the underlying queryset (slicing) to avoid API bloat. 0-indexed because the audience is data analysts who expect Python/SQL conventions.
- **v2.2 (2026-05-19, addendum after dogfooding step 2 + v2.1):** added `boundary_timeline(type)` (the killer-feature timeline view), `geoid_on(type, date)`, `current_geoid(type)`. Documentation amends on existing methods cover sparse-geoid-fill, timezone dependency, and NULL ordering. Filed the "perf: single-type fetches all periods" observation as a follow-up; does not block this step. Surface total is now seven public read methods, weighed and held.

---


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
