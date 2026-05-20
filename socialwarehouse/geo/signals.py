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
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_signal_state = threading.local()


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

        if dirty_fields:
            addr.save(update_fields=dirty_fields)
            updated_count += 1

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
        for btype in Address._BOUNDARY_TYPES:
            new_value = getattr(instance, f"{btype}_geoid", "") or ""
            if not new_value:
                # ABP row doesn't carry this boundary type's geoid;
                # don't clobber existing cache from another ABP row.
                continue
            cache_field = f"{btype}_geoid"
            if getattr(addr, cache_field) != new_value:
                setattr(addr, cache_field, new_value)
                dirty_fields.append(cache_field)

        if dirty_fields:
            addr.save(update_fields=dirty_fields)
            logger.debug(
                "F11 step-2b: refreshed Address %s cache fields %s from ABP %s",
                addr.pk, dirty_fields, instance.pk,
            )
