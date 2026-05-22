"""Signal handlers that keep Address-level cached GEOIDs in lockstep with
AddressBoundaryPeriod (ABP) writes.

F11 step 2b: the cache-coherence invariant. When an ABP row for a
*current* vintage is written, the corresponding `Address.{type}_geoid`
cache fields are updated in the same transaction. The cache becomes
formally "current-by-construction."

Definitions (per F11 step-2b design v2):
    - A vintage is *current* if its [effective_from, effective_to)
      window contains today. effective_to=NULL means "unreplaced,
      still in effect."
    - The cache is *coherent* if Address.{type}_geoid equals
      Address.current_boundaries()[type].{type}_geoid for every
      boundary type the address has rows for.

The handler bails out cheaply (no DB read) when the ABP's vintage is
not current; this keeps backfills of historical vintages from
polluting the cache or paying per-write Address lookup cost.

Backfill / bulk-write callers can temporarily disable the signal with
:func:`address_cache_refresh_disabled` and call
:func:`refresh_address_caches` explicitly after the bulk write
completes.

This module is wired up by :class:`socialwarehouse.geo.apps.GeoConfig`.
"""

import contextlib
import logging
import threading
from datetime import date

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

logger = logging.getLogger(__name__)

_signal_state = threading.local()


# SW#200: downstream cascade event.
#
# Fires after the F11 step-2b cache-coherence handler updates one or
# more `Address.{type}_geoid` (or `Address.census_year`) fields. Lets
# downstream consumers — e.g. the FEC analysis project's fact tables —
# react to a coherent change without F11 needing to know about them.
#
# Kwargs:
#   sender         — Address (the model class)
#   instance       — Address (the row whose cache changed)
#   dirty_fields   — list[str] of the field names that were updated
#   source_abp     — AddressBoundaryPeriod | None — the ABP whose save
#                    triggered the update; None when fired from the
#                    bulk `refresh_address_caches` path.
#
# Contract:
#   - In-process synchronous: subscribers run in the same DB transaction
#     as the originating ABP write. Raise to roll back the originating
#     write; return cleanly to commit.
#   - Subscribers MUST be idempotent. The signal may fire on a no-op
#     cache rewrite if a future refactor changes the dirty-detection.
#   - Subscribers MUST NOT do slow I/O on the dispatch thread (HTTP
#     calls, large batch DB writes). Enqueue background work and return.
#
# Runtime evolution note:
#   When the FEC analysis project (or any subscriber) needs cross-process
#   notification — Celery workers, Airflow DAG triggers — replace this
#   in-process Django Signal with a Celery `send_task` (or equivalent
#   broker dispatch) inside the same handler. Airflow can subscribe to
#   the broker via a sensor task. The kwargs contract above is the
#   stable interface; only the transport changes.
address_boundary_cache_changed = Signal()


@contextlib.contextmanager
def address_cache_refresh_disabled():
    """Temporarily suppress the ABP-post_save cache-refresh signal.

    Use inside bulk-write contexts (`assign_boundaries` batch loops,
    test fixtures, etc.) where the caller will explicitly invoke
    :func:`refresh_address_caches` after the bulk write completes.

    Thread-local; concurrent calls in other threads are unaffected.
    """
    prev = getattr(_signal_state, "disabled", False)
    _signal_state.disabled = True
    try:
        yield
    finally:
        _signal_state.disabled = prev


def _census_year_from_vintage(vintage):
    """Return decade int from a census-decadal vintage, else None.

    SW#100: Address.census_year is the canonical denormalized year hint
    for the address. The signal maintains it from the polymorphic Vintage
    parent — only census-decadal kinds update census_year (ACS / BLS /
    redistricting vintages do not represent "the Census decade").

    `vintage` may be either the parent `Vintage` instance (from an ABP
    FK access) or the `CensusDecadalVintage` subclass directly.
    """
    if vintage is None or vintage.kind != "census-decadal":
        return None
    # Subclass instance — `decade` is a direct attribute.
    decade = getattr(vintage, "decade", None)
    if decade is not None:
        return decade
    # Parent Vintage — downcast.
    decadal = getattr(vintage, "censusdecadalvintage", None)
    return decadal.decade if decadal is not None else None


def _is_current_vintage(vintage, today=None):
    """Return True if `vintage`'s effective window contains today.

    Reads `vintage.effective_from` and `vintage.effective_to` directly.
    `effective_to=None` means "unreplaced, still in effect."
    """
    if vintage is None:
        return False
    today = today or date.today()
    if vintage.effective_from and vintage.effective_from > today:
        return False
    if vintage.effective_to is not None and vintage.effective_to <= today:
        return False
    return True


def refresh_address_caches(addresses, today=None):
    """Recompute and write cached GEOIDs for each Address in `addresses`.

    Used after a bulk-write block that suppressed the per-row signal
    (see :func:`address_cache_refresh_disabled`). For each address,
    pulls the current boundaries via `Address.current_boundaries()`
    and writes any changed `{type}_geoid` fields in a single UPDATE
    per address.

    `addresses` may be a queryset, list, or any iterable of Address
    instances. Returns the number of addresses whose cache fields
    were updated.

    Today's date defaults to `timezone.localdate()`; pass `today` for
    deterministic tests.
    """
    from django.utils import timezone
    from socialwarehouse.geo.models import Address

    today = today or timezone.localdate()
    updated_count = 0

    for addr in addresses:
        result = addr.boundaries_on(today)
        dirty_fields = []
        for btype in Address._BOUNDARY_TYPES:
            cache_field = f"{btype}_geoid"
            row = result.get(btype)
            new_value = getattr(row, cache_field, "") if row else ""
            new_value = new_value or ""
            if getattr(addr, cache_field) != new_value:
                setattr(addr, cache_field, new_value)
                dirty_fields.append(cache_field)

        # SW#100: maintain census_year from the most recent census-decadal
        # ABP row's vintage. boundaries_on returns the per-type ABP rows
        # that are active today; any of them tied to a census-decadal
        # vintage tells us the decade.
        for row in result.values():
            if row is None:
                continue
            year = _census_year_from_vintage(row.vintage)
            if year is not None and addr.census_year != year:
                addr.census_year = year
                if "census_year" not in dirty_fields:
                    dirty_fields.append("census_year")
                break

        if dirty_fields:
            addr.save(update_fields=dirty_fields)
            updated_count += 1
            address_boundary_cache_changed.send(
                sender=Address,
                instance=addr,
                dirty_fields=list(dirty_fields),
                source_abp=None,
            )

    return updated_count


def _connect():
    """Connect the signal. Called from GeoConfig.ready()."""
    from socialwarehouse.geo.models import Address, AddressBoundaryPeriod

    @receiver(post_save, sender=AddressBoundaryPeriod, dispatch_uid="f11_step2b_address_cache_refresh")
    def refresh_address_cache_on_abp_write(sender, instance, raw=False, **kwargs):
        if raw:
            # Fixture loads: skip the signal so test setup doesn't
            # cascade-update.
            return
        if getattr(_signal_state, "disabled", False):
            return
        if not _is_current_vintage(instance.vintage):
            # Backfill / historical write; cache untouched.
            return

        addr = instance.address
        dirty_fields = []

        # SW#228: identify which boundary types the saved ABP touches;
        # we only need to re-resolve the cache for those types.
        types_touched = [
            btype for btype in Address._BOUNDARY_TYPES
            if (getattr(instance, f"{btype}_geoid", "") or "")
        ]

        # SW#228 fix (option b): instead of trusting `instance.{btype}_geoid`
        # directly (which loses the cache-vs-helper invariant when ABP rows
        # are INSERTed out of context_date order), re-resolve the
        # authoritative current value per type via `boundaries_on(today,
        # boundary_types=types_touched)`. The cache then matches what
        # `current_boundaries()` / `current_geoid()` would return for the
        # same address at the same moment, regardless of INSERT order.
        #
        # The single grouped call (vs N per-type calls) leverages the
        # SW#188 type-filter pushdown on boundaries_on — one DB query
        # rather than N — so the correctness fix here doesn't come with
        # an N-times-DB cost.
        if types_touched:
            from django.utils import timezone
            today = timezone.localdate()
            authoritative = addr.boundaries_on(today, boundary_types=types_touched)
            for btype in types_touched:
                authoritative_row = authoritative.get(btype)
                if authoritative_row is None:
                    # No current ABP for this type — saved instance must
                    # be a backfill / historical write that doesn't shift
                    # "current" semantics. Don't clobber cache.
                    continue
                new_value = getattr(authoritative_row, f"{btype}_geoid", "") or ""
                cache_field = f"{btype}_geoid"
                if getattr(addr, cache_field) != new_value:
                    setattr(addr, cache_field, new_value)
                    dirty_fields.append(cache_field)

        # SW#100: also maintain census_year from census-decadal vintages.
        new_year = _census_year_from_vintage(instance.vintage)
        if new_year is not None and addr.census_year != new_year:
            addr.census_year = new_year
            dirty_fields.append("census_year")

        if dirty_fields:
            addr.save(update_fields=dirty_fields)
            logger.debug(
                "F11 step-2b: refreshed Address %s cache fields %s from ABP %s",
                addr.pk, dirty_fields, instance.pk,
            )
            address_boundary_cache_changed.send(
                sender=Address,
                instance=addr,
                dirty_fields=list(dirty_fields),
                source_abp=instance,
            )
