# F11 step 2b / SW#100 — Signal-driven cache refresh (design)

**Status:** Design v2. Q1 answered (2026-05-19). Q2-Q4 elaborated with concrete options + trade-offs per the maintainer's "please elaborate" requests.

## Resolved decisions (v2)

### Q1: "current" is defined by the vintage's effective window

> "current should return a temporal window that includes now. Vintages, as such, should have an effective date from X to NOW(), meaning, unreplaced. This requires a lot of administrative upkeep, but it can be a management command run on a schedule to update."

A vintage is **current** if its `[effective_from, effective_to)` window contains today, where `effective_to=NULL` means "unreplaced, still in effect." The signal recognizes "current" by examining the vintage's window — NOT by the ABP's `context_date` or write order.

Handler check:

```python
def _is_current_vintage(vintage, today):
    if vintage.effective_from and vintage.effective_from > today:
        return False
    if vintage.effective_to is not None and vintage.effective_to <= today:
        return False
    return True
```

An ABP write whose vintage's effective_to has already passed does NOT refresh the cache. This means backfilling historical (already-superseded) vintages doesn't pollute the cache — exactly the right semantic for the cache being "today's authoritative answer."

**Administrative upkeep:** A new management command `seal_superseded_vintages` runs on a schedule (nightly is plenty) and sets `vintage.effective_to = today` for vintages superseded by a newer one of the same kind / domain. Today's "unreplaced" vintage is the one with `effective_to IS NULL`. This is the canonical write-side maintenance step the user named.

This Q1 answer depends on Vintage having `effective_from / effective_to` fields. Sequencing options:
- **(seq-a)** Land step-2b's implementation against the polymorphic Vintage from sub-issue B (#190). Cleaner; gated on B landing.
- **(seq-b)** Land step-2b first against the existing `CensusVintageConfig.effective_start / effective_end` (integer years; convert to date with `date(year, 1, 1)` and `date(year + 1, 1, 1)` for the half-open semantics). Then migrate to polymorphic Vintage in B.

(seq-a) is cleaner; (seq-b) decouples the schedules. The implementation PR picks based on B's landing cadence.

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

### Q2. Should the signal run during backfills? (elaboration)

The thing that makes backfill dangerous for the signal is not the volume per se — it's the per-write cost. With Q1 answered, the handler does:
1. Check `_is_current_vintage(instance.vintage, today)`. Cheap (no DB).
2. If yes, SELECT the Address row (one query).
3. Diff cache fields vs incoming. In-memory.
4. If any changed, UPDATE the Address row (one query).

At backfill cadence (thousands of ABP rows / second is plausible), that's thousands of extra Address SELECTs and UPDATEs per second. The handler is correct; it's just expensive.

Three options for handling backfill, each with concrete shapes:

#### (a) Always fire — never suppress

**Shape:** signal fires on every ABP write. No special case for backfills.

**Pros:**
- One code path. No "did the backfill remember to suppress?" failure mode.
- Cache is always consistent with whatever was just written, transactionally.

**Cons:**
- Backfills do 2N extra queries per address (one SELECT + one UPDATE per ABP write, even for non-current vintages, because the handler has to check vintage's effective range).
- Actually: with Q1's `_is_current_vintage` check, backfills of HISTORICAL vintages skip the SELECT — `_is_current_vintage` short-circuits before hitting the DB. So the cost is only for current-vintage writes. That's not bad.

**When (a) is right:** if 95%+ of backfilled ABP writes are historical (already-superseded vintages), (a) is effectively free.

#### (b) Context-manager-suppressed during bulk

**Shape:**

```python
# socialwarehouse/geo/signals.py
import contextlib
import threading

_signal_disabled = threading.local()

@contextlib.contextmanager
def address_cache_refresh_disabled():
    """Temporarily suppress the ABP-post_save signal for cache refresh.
    
    Use inside bulk-write contexts where the caller will explicitly
    invoke `refresh_address_caches(...)` after the bulk write completes.
    """
    _signal_disabled.value = True
    try:
        yield
    finally:
        _signal_disabled.value = False

@receiver(post_save, sender=AddressBoundaryPeriod)
def refresh_address_cache_on_abp_write(sender, instance, **kwargs):
    if getattr(_signal_disabled, "value", False):
        return
    # ... normal handler logic ...

# Bulk caller (assign_boundaries):
with address_cache_refresh_disabled():
    AddressBoundaryPeriod.objects.bulk_create(rows)
refresh_address_caches(Address.objects.filter(pk__in=address_ids))
```

**Pros:**
- Backfills explicitly opt out. The bulk-write site documents its own behavior.
- `refresh_address_caches` can be a single batched query (one UPDATE per address with all cache fields set in one go).

**Cons:**
- Backfill paths must remember to suppress + refresh. If they forget the refresh, cache drifts.
- Thread-local state adds a small footgun in concurrent contexts (Celery worker pools, etc.) — the context manager is per-thread, so concurrent backfills in different threads are isolated, but a poorly-timed signal from a sibling code path inside the same thread would also be suppressed.

#### (c) Rely on bulk_create's natural signal-skipping

**Shape:** Django's `bulk_create()` does NOT fire post_save signals by default. If backfill paths use `bulk_create`, the signal naturally doesn't fire.

**Pros:**
- Zero code in the signal handler / SW; the suppression is just an artifact of Django's bulk-API behavior.
- No thread-local state.

**Cons:**
- Backfill paths must use `bulk_create`. The current `assign_boundaries.py` uses per-row `update_or_create` (line 243+); converting that to a bulk-API call is a non-trivial refactor.
- Misses ABP writes from callers that DO use per-row writes for legitimate reasons (e.g., partial reassignment on the order-of-a-few-addresses; the signal SHOULD fire there).
- Behavior is silently coupled to which Django ORM call the caller picks. A future caller using `.save()` per-row inside a "bulk" job would fire the signal without realizing it.

#### Recommendation

**(b) context-manager-suppressed.** Reasoning:
- (a) is acceptable IF most backfilled vintages are historical; but the implementation is no simpler than (b) once `_is_current_vintage` is in the handler. (b) gives explicit control for the actual-current-vintage-bulk-load case (e.g., the 2030 census drop).
- (c) couples behavior to Django API choices in callers — fragile.
- (b) is explicit, scoped to known bulk-write sites, and the `refresh_address_caches(qs)` helper centralizes the post-bulk update logic so it can be tested.

If you disagree, the next-most-defensible is (a) — accept the per-write cost as the simplicity payback.

### Q3. Should a signal-driven refresh fire downstream cascades? (elaboration)

When an Address's cache fields update, several downstream things become potentially stale. Concretely, what's downstream of `Address.cd_geoid`:

1. **Warehouse fact tables.** `FactRedistrictingPlan`, `FactDonor`, etc. — anything that joined an Address to a CD at the time of insertion.
2. **DimGeography rollups.** If DimGeography records aggregate per-CD-per-vintage stats, an address moving CDs changes those rollups.
3. **Materialized views / cached queries.** Any "addresses in CD-12" materialized view would need to drop the now-not-in-CD-12 address.
4. **Downstream pipeline jobs.** Voter outreach lists, geographic enrichment, etc.
5. **External-facing API responses.** Any cached `/api/address/<id>/boundaries` response.

Three options for handling this, each with concrete shapes:

#### (a) No cascade in this PR

**Shape:** the signal handler updates only `Address.{type}_geoid`. Nothing else fires.

**Consequence:** downstream consumers are responsible for re-reading at their own cadence. Fact tables that joined-and-cached the geoid at insertion stay stale until they're rebuilt; materialized views go stale until the next refresh; API caches go stale until their TTL expires.

**Pros:**
- Tightly scoped PR. The cache-coherence invariant is achievable AND testable in isolation.
- No coupling to specific downstream paths; each can adopt its own refresh strategy.

**Cons:**
- Stale downstream state until each consumer is independently fixed. Discovered as "weird query result" rather than "well-documented invariant."
- Pushes the same problem (cache vs source-of-truth) one layer out. We solve it for Address; we don't solve it for FactRedistrictingPlan.

#### (b) Cascade to a single derived path (e.g., DimGeography)

**Shape:** add ONE more signal handler that listens for `Address.cd_geoid` (etc.) changes via Django's `post_save` on `Address` with `update_fields` inspection. When triggered, it enqueues a `refresh_dim_geography_for_address(address_id)` task (Celery or sync).

**Pros:**
- Solves the most-visible downstream-staleness problem (DimGeography is the warehouse's central reporting surface).
- Pattern is repeatable: each future downstream gets its own handler.

**Cons:**
- Picks a winner. DimGeography is the most-visible BUT not the only consumer. The "if you didn't get a handler, you're on your own" pattern is uncomfortable.
- Adds Celery / async dependency to F11's signal path. Step-2b's PR becomes "signal + Celery task + DimGeography refresh logic" — three things to test together.

#### (c) Generic event-bus shape

**Shape:** define a domain event (Python dataclass, signal, or `django-signal-disabler`-style event):

```python
class AddressBoundaryChangedEvent:
    address_id: int
    changed_boundary_types: list[str]
    old_values: dict[str, str]
    new_values: dict[str, str]
    timestamp: datetime

# Step-2b emits the event after the cache update.
# Downstream consumers subscribe to the event in their own apps.
```

**Pros:**
- Decoupled. Step-2b's PR ships the cache invariant + the event emission. Each downstream consumer ships its own subscriber in its own PR.
- Future-proof: new downstream paths just subscribe; no F11 changes needed.

**Cons:**
- Bigger architectural decision. Picking the event-bus mechanism (Django signals, Celery messages, custom registry) shapes how every future cross-app coupling works.
- Step-2b becomes the place where SW commits to an event-bus pattern. That's a real decision that shouldn't be made inside an F11 step-2b PR.

#### Recommendation

**(a) for step 2b's PR; file follow-up tickets for the downstream cascade decision.** Reasoning:
- (b) and (c) both make step-2b's PR substantially larger AND introduce architectural decisions that aren't F11's responsibility.
- (a) ships the cache-coherence invariant cleanly. Whichever downstream cascade strategy lands later can build on top of the now-correct Address.cache.
- File a parent follow-up ticket: "Downstream cascade strategy after F11 step-2b lands" — that ticket explicitly picks between (b) and (c) and is sub-divided per-downstream-consumer.

If you want (b) instead, the implementation shape works but the PR doubles in size and Celery enters the dependency.

### Q4. How do we test it? (elaboration)

Two layers of test, each with concrete shapes:

#### (a) Unit tests on the signal handler

**Shape:** TestCase-style tests that exercise the signal directly. Examples:

- `test_current_vintage_abp_write_updates_cache`: create ABP with current-vintage; assert `Address.cd_geoid` matches after save.
- `test_superseded_vintage_abp_write_does_not_update_cache`: create ABP with a vintage whose effective_to is in the past; assert cache unchanged.
- `test_unchanged_value_no_update`: write an ABP whose cache-fields match the current Address state; assert no extra UPDATE fires (mock or instrument the DB to count writes).
- `test_disable_context_manager_suppresses_signal`: write ABP inside `with address_cache_refresh_disabled():`; assert cache unchanged; assert explicit `refresh_address_caches(qs)` does update.
- `test_raw_load_skips_signal`: load ABP via fixture (raw=True); assert cache unchanged.
- `test_partial_geoid_only_updates_present_fields`: ABP row has cd_geoid but null sldl_geoid; assert only cd cache field updates, sldl cache untouched.

**Pros:** pins each handler branch explicitly. Easy to read; failures point at the exact branch.

**Cons:** tests the handler's contract, not the cache-vs-helper invariant. If the handler "works" but doesn't match what `current_boundaries()` would compute, unit tests won't catch the divergence.

#### (b) Property test on the cache-vs-helper invariant

**Shape:** with hypothesis (or a hand-rolled randomizer), generate sequences of ABP writes; after each, assert the invariant:

```python
@given(abp_write_sequences())
def test_cache_matches_helper_after_any_write_sequence(writes):
    addr = Address.objects.create(...)
    for write in writes:
        AddressBoundaryPeriod.objects.create(address=addr, **write)
        addr.refresh_from_db()
        helper_result = addr.current_boundaries()
        for btype in Address._BOUNDARY_TYPES:
            cached = getattr(addr, f"{btype}_geoid")
            from_helper = helper_result.get(btype)
            helper_geoid = getattr(from_helper, f"{btype}_geoid", "") if from_helper else ""
            assert cached == helper_geoid, (
                f"Cache/helper mismatch for {btype} after writes: "
                f"cache={cached!r}, helper={helper_geoid!r}"
            )
```

**Pros:** catches the actual invariant (the user-visible contract). Catches subtle ordering issues — out-of-order ABP writes, partial-vintage rows, etc. — that hand-picked unit tests would miss.

**Cons:** requires hypothesis as a test dependency (already in SW? check). Test failures can be hard to reduce to a minimal reproducer; hypothesis's shrinking helps but isn't free. Property tests are slower than unit tests.

#### Recommendation

**Ship (a) in step-2b's PR. File (b) as a follow-up.**

Reasoning:
- (a) covers every named branch in the handler. That's the "did I write the handler correctly?" question.
- (b) covers the "is the contract right?" question. It's higher value but more invasive — hypothesis dependency, longer test runs, more shrinking-failure noise.
- A reasonable middle ground: ship one hand-rolled multi-write integration test in (a)'s suite (the "ten-write sequence" case) that exercises the most-likely real-world pattern without going full property-test. That covers 80% of (b)'s value without the hypothesis dependency.

If you want (b), the follow-up's scope is "add hypothesis to SW dev deps; convert the ten-write integration test from (a) into a property test; remove the hand-rolled version."

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
