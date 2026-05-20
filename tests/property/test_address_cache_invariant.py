"""Hypothesis property test on the F11 step-2b cache-vs-helper invariant.

SW#201: catches subtler issues than hand-rolled tests can — partial-fill
ABP rows, varied geoid combinations, context-date variation. Pins:

    After ANY sequence of `AddressBoundaryPeriod` writes for the current
    vintage applied in context_date order, for every boundary type `t`,
    `Address.t_geoid` equals `Address.current_boundaries()[t].t_geoid`
    (or both are absent / empty).

Maintainer's call on the runtime budget (SW#201 thread): shape (a) —
every PR, ~30s budget, max_examples=50, deadline=None. F11 step-2b is
load-bearing for every Address-boundary read; coherence breaks corrupt
downstream data quietly.

Notes:
- Restricted to a 3-type subset (cd / sldl / sldu) to keep the strategy
  shrinkable and the per-example DB churn modest. Property scales to
  the full _BOUNDARY_TYPES tuple if a later run wants it.
- Writes are applied in ascending context_date order. The current
  signal overwrites cache in INSERT order; helper picks the row with
  the most-recent context_date. Out-of-order inserts violate the
  invariant (tracked as SW#228). Once that lands, this test drops the
  ordering constraint and the broader property ships.
- Uses the seeded 2020 CensusDecadalVintage (current as of "today" in
  the test); historical/future-vintage paths are covered by the
  hand-rolled tests in test_address_cache_signal.py.
"""

from datetime import date

from hypothesis import HealthCheck, given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase


# Three boundary types — enough variety for partial-fill writes, small
# enough to keep examples fast.
_TYPES = ("cd", "sldl", "sldu")

# Plausible geoid values per type. Real GEOIDs are longer, but the
# invariant doesn't care about format — only that the strings round-trip
# through the cache and the helper unchanged.
_GEOID_ALPHABET = "0123456789"


def _geoid_strategy():
    """Either an empty string (skip this type in the ABP row) or a short
    digit-only token. Capped at 4 chars — that's `cd_geoid`'s column
    width (the narrowest of the three tested types)."""
    return st.one_of(
        st.just(""),
        st.text(alphabet=_GEOID_ALPHABET, min_size=2, max_size=4),
    )


def _abp_write_strategy():
    """One ABP write spec: per-type geoid choice. context_date is
    assigned by the test from a unique-ascending sequence to avoid
    Django ORDER BY tiebreaker nondeterminism."""
    return st.fixed_dictionaries({
        "cd": _geoid_strategy(),
        "sldl": _geoid_strategy(),
        "sldu": _geoid_strategy(),
    })


class TestCacheVsHelperInvariant(HypothesisTestCase):
    """Property: after a random sequence of current-vintage ABP writes,
    the cache and the helper agree.
    """

    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    @given(writes=st.lists(_abp_write_strategy(), min_size=1, max_size=12))
    def test_cache_matches_helper(self, writes):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusDecadalVintage,
        )

        vintage = CensusDecadalVintage.objects.get(decade=2020)
        addr = Address.objects.create(state_abbreviation="CA")

        # Apply writes in ascending order with strictly-unique
        # context_date per write (i + offset days from a base). This
        # eliminates ORDER BY tiebreaker nondeterminism in the helper.
        from datetime import timedelta
        base = date(2024, 1, 1)
        for i, w in enumerate(writes):
            if not any(w[t] for t in _TYPES):
                continue
            AddressBoundaryPeriod.objects.create(
                address=addr,
                vintage=vintage,
                cd_geoid=w["cd"],
                sldl_geoid=w["sldl"],
                sldu_geoid=w["sldu"],
                context_date=base + timedelta(days=i),
                # Vary plan id per write so the (address, vintage, plan)
                # unique constraint (nulls_distinct=False) allows the
                # full sequence. db_constraint isn't enforced on the FK
                # so a fake int id is fine for the test.
                redistricting_plan_id=i + 1,
                assignment_method="SPATIAL_JOIN",
            )

        addr.refresh_from_db()
        current = addr.current_boundaries()

        for btype in _TYPES:
            cache_val = getattr(addr, f"{btype}_geoid", "") or ""
            helper_row = current.get(btype)
            helper_val = (
                getattr(helper_row, f"{btype}_geoid", "") or ""
            ) if helper_row else ""
            assert cache_val == helper_val, (
                f"cache vs helper mismatch for {btype!r}: "
                f"cache={cache_val!r}, helper={helper_val!r}, "
                f"writes={writes}"
            )
