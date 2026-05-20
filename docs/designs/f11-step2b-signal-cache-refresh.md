# F11 step 2b / SW#100 — Signal-driven cache refresh (design)

**Status:** Design v1. No code. Awaiting maintainer answers to four
questions before implementation.

## Context

F11's v2 design answer to Q2 was **(a) signal-driven** — every ABP write
that lands a new "current" period for an address updates the
Address-level cached GEOID fields (`Address.cd_geoid`, `Address.sldl_geoid`,
...) in the same transaction. Step 2 (PR #187, merged) added the
read-side helpers that treat ABP as authoritative; step 2b is the
write-side counterpart that keeps the cache in lockstep.

Why this matters: any caller doing `Address.objects.filter(cd_geoid="0612")`
is implicitly asking "currently in CD 06-12." Without the signal, that
filter silently returns stale results when an ABP write lands a new
current assignment that doesn't update the cache.

## Goal

After step 2b lands:

- For every ABP write that represents a new "current" assignment for an
  address, the corresponding `Address.{type}_geoid` cache fields are
  updated in the same transaction.
- `Address.current_boundaries()` and `Address.current_geoid(type)` return
  the same values as reading the cache directly.
- No caller migrations needed in this PR — callers using the cache
  continue to work; callers using the helpers continue to work; both
  agree on the answer.

## Where the signal fires

`AddressBoundaryPeriod` is the trigger. The choice is `post_save` vs
`pre_save`:

- **`post_save`**: row is already in the DB when the handler runs.
  Handler reads the row, decides what to do, updates `Address` if
  needed. Simpler; matches Django convention for "do something
  consequent to this write."
- **`pre_save`**: handler runs before the row hits the DB. Can mutate
  the row in flight, but for our use case (updating a *different*
  model) there's no advantage.

**Recommended: `post_save`.**

## Algorithm sketch

```python
@receiver(post_save, sender=AddressBoundaryPeriod)
def refresh_address_cache_on_abp_write(sender, instance, created, raw, **kwargs):
    if raw:
        # Loading fixtures — skip the signal so fixtures don't
        # trigger cascading updates during test setup.
        return

    if not _is_current_for_today(instance):
        # The ABP row doesn't represent the *current* assignment.
        # Historical / backfill writes don't refresh the cache.
        return

    addr = instance.address
    dirty = False
    for btype in Address._BOUNDARY_TYPES:
        new_value = getattr(instance, f"{btype}_geoid", None) or ""
        if not new_value:
            continue  # this row doesn't carry that boundary type
        cache_field = f"{btype}_geoid"
        if getattr(addr, cache_field) != new_value:
            setattr(addr, cache_field, new_value)
            dirty = True

    if dirty:
        # Update only the cache fields + an updated_at so the signal
        # we're handling doesn't recursively fire from a full save().
        addr.save(update_fields=[f"{t}_geoid" for t in Address._BOUNDARY_TYPES])
```

The handler is intentionally narrow: it only updates `{type}_geoid`
fields, and only when they would change. Other Address fields aren't
touched. The `update_fields=...` argument ensures Django emits a
narrow UPDATE statement, not a full row write.

## Four open questions for the maintainer

### Q1. What does "current" mean for the signal?

Three candidate definitions:

- **(a) Most-recent-context_date on this address.** "Current" = the ABP
  row whose `context_date` is the latest among this address's ABP
  rows. If the new write has the latest `context_date`, refresh the
  cache.
- **(b) Today's active period.** Compute `boundaries_on(today)`; if
  the result includes this ABP row, refresh.
- **(c) Both.** Refresh if (a) OR (b).

**My read: (a).** It's the cheapest (no per-write `boundaries_on`
call) and matches the read-side `boundary_history`'s ordering. It does
mean that an ABP write with a future `context_date` updates the cache
today even if the assignment isn't yet "in effect" — but that's
arguably right, because the cache reflects "what assign_boundaries last
believed," which IS the future-dated row once it's written.

### Q2. Should the signal run during backfills?

When `assign_boundaries` is run against a fresh DB or after a multi-
year backfill, thousands of ABP writes land in succession. The signal
would fire on every one, doing a per-write Address SELECT + UPDATE.
Three options:

- **(a) Always fire.** Simplest. At backfill scale, this is N extra
  UPDATEs per address (one per ABP write). Quadratic in the worst case
  if backfill iterates addresses many times.
- **(b) Skip during a context flag.** Add a `with disable_signal():`
  context manager (or thread-local) that backfill commands can use to
  suppress the signal. After the bulk write, the command calls a
  separate `refresh_address_caches(qs)` function to do the update in
  bulk.
- **(c) Use `bulk_create` / `bulk_update` discipline.** Django signals
  don't fire on `bulk_create` by default. If backfills are rewritten
  to use bulk operations, the signal naturally doesn't run; backfills
  then must explicitly call a refresh helper.

**My read: (b).** (a) is fine for ad-hoc writes but unacceptable at
backfill scale. (c) requires rewriting backfill paths; (b) is a
smaller change. The context manager is one extra line at the bulk-
write site in `assign_boundaries` and similar.

### Q3. Should a signal-driven refresh fire DimGeography / downstream cascades?

`Address.{type}_geoid` is read by several downstream paths (warehouse
enrichment, geocode pipeline, analytics queries). When the cache
updates, do we want a cascade — for example, to invalidate a
warehouse-fact-table cache, or re-enqueue a downstream pipeline job?

Three options:

- **(a) No cascade.** Step 2b only updates the Address row. Downstream
  consumers are responsible for re-reading at their own cadence.
- **(b) Cascade to a single derived path.** Pick one (e.g.,
  `DimGeography`) and add a follow-up signal there.
- **(c) Generic event-bus shape.** Emit an "address-boundary-changed"
  domain event; downstream consumers subscribe.

**My read: (a) for this PR; (b) or (c) as separate future tickets.**
The signal's job is the cache-coherence invariant. Downstream cascades
are a different concern that shouldn't be tangled into this PR.

### Q4. How do we test it?

Unit tests at the signal level are straightforward (create ABP, assert
Address row's cache updated). The harder question is: do we want a
*property-style* test that asserts the cache and the helpers agree
after a sequence of writes?

- **(a) Unit tests only.** Pin the behavior on a few representative
  cases.
- **(b) Property test.** Run a randomized sequence of ABP writes;
  after each one, assert
  `Address.current_boundaries()[t].{t}_geoid == Address.{t}_geoid`
  for every type the address has rows for.

**My read: (a) for this PR; (b) is a nice-to-have follow-up.** Unit
tests cover the contract; property test would catch subtler ordering
issues but is a non-trivial test-infrastructure addition.

## What this PR delivers

Just the design note. Sign-off pattern:

1. **Answer Q1-Q4** above.
2. I open a follow-up PR with the signal handler + the `with
   disable_signal()` context manager + unit tests.
3. Update `assign_boundaries.py` to use the context manager during
   bulk runs, with an explicit refresh call after the bulk write.
4. Update existing F11 step-2 helper docstrings (`current_boundaries`,
   `current_geoid`) to drop the "until step-2b lands" caveat — the
   cache is now formally "current-by-construction."

## Risk

- **Signal storms during backfill** if Q2 is answered (a). Could
  dramatically slow `assign_boundaries` runs that touch all addresses.
- **Cache drift** if the signal fails silently. The handler should
  log on any branch it bails out of (raw=True, not-current, etc.) at
  debug level so failures are visible without spamming production logs.
- **Test-time pollution** if signal handlers aren't disconnectable in
  tests. The implementation should use Django's `signals.receiver`
  decorator with an importable handler name so tests can opt out.

## Sequencing

- This PR (design v1): sign-off on Q1-Q4. **← here.**
- Implementation PR: handler + context manager + unit tests + caller
  update in `assign_boundaries.py`.
- Follow-up tickets (filed after impl lands): property test (Q4 (b)),
  downstream cascade design (Q3 (b)/(c)) — both optional.

## References

- Parent: F11 / SW#100.
- Initiative: SW#189 (template-readiness; this is sub-issue A in the
  parent's checklist).
- Step 2 (read-side helpers): merged via SW#187.
- Step 2 design: docs/designs/f11-address-temporal-boundary-history.md
  (now at v2.2; this design references its decisions).
