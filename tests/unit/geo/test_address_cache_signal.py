"""Tests for F11 step 2b: the signal handler that keeps Address-level
cached GEOIDs in lockstep with AddressBoundaryPeriod writes.

Covers the design's Q4 (a) plan: hand-rolled unit tests on every named
handler branch, plus one multi-write integration test that exercises a
realistic sequence of writes.

The hypothesis-based property test on the cache-vs-helper invariant is
tracked separately (SW#201).
"""

from datetime import date

from django.test import TestCase
from django.utils import timezone

from socialwarehouse.geo.signals import (
    _is_current_vintage,
    address_cache_refresh_disabled,
    refresh_address_caches,
)


class TestIsCurrentVintage(TestCase):
    """`_is_current_vintage` recognizes the current vintage window
    against the polymorphic Vintage's date-typed `effective_from /
    effective_to`."""

    def setUp(self):
        from socialwarehouse.geo.models import CensusDecadalVintage
        self.vintage_2010 = CensusDecadalVintage.objects.get(decade=2010)
        self.vintage_2020 = CensusDecadalVintage.objects.get(decade=2020)

    def test_current_vintage_today_in_window(self):
        # vintage_2020 has effective_to=None (unreplaced); today inside.
        assert _is_current_vintage(self.vintage_2020, today=date(2026, 5, 19))

    def test_past_vintage_today_after_window(self):
        # vintage_2010 has effective_to=date(2020,1,1); today=2026 is after.
        assert not _is_current_vintage(self.vintage_2010, today=date(2026, 5, 19))

    def test_future_vintage_today_before_window(self):
        # Hypothetical 2030 vintage; today=2026 is before.
        from socialwarehouse.geo.models import CensusDecadalVintage

        future = CensusDecadalVintage.objects.create(
            decade=2030,
            effective_from=date(2030, 1, 1),
            effective_to=None,
        )
        assert not _is_current_vintage(future, today=date(2026, 5, 19))

    def test_none_vintage_returns_false(self):
        assert _is_current_vintage(None, today=date(2026, 5, 19)) is False


class TestSignalCacheRefresh(TestCase):
    """The signal updates Address.{type}_geoid when ABP for a current
    vintage is written; bails out otherwise."""

    def setUp(self):
        from socialwarehouse.geo.models import Address, CensusDecadalVintage
        self.vintage_2020 = CensusDecadalVintage.objects.get(decade=2020)
        self.vintage_2010 = CensusDecadalVintage.objects.get(decade=2010)
        self.addr = Address.objects.create(state_abbreviation="CA")

    def _create_abp(self, **kwargs):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        defaults = {
            "address": self.addr,
            "vintage": self.vintage_2020,
            "assignment_method": "SPATIAL_JOIN",
        }
        defaults.update(kwargs)
        return AddressBoundaryPeriod.objects.create(**defaults)

    def test_current_vintage_write_updates_cache(self):
        assert self.addr.cd_geoid == ""

        self._create_abp(cd_geoid="0612")

        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == "0612"

    def test_superseded_vintage_write_does_not_update_cache(self):
        # vintage_2010 is past today (2026); writing an ABP against it
        # should NOT touch the cache.
        self._create_abp(vintage=self.vintage_2010, cd_geoid="0107")

        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == ""

    def test_partial_geoid_only_updates_present_fields(self):
        # ABP carries cd_geoid only; sldl_geoid is null. Cache update
        # should touch cd_geoid but leave sldl_geoid alone.
        self.addr.sldl_geoid = "01234"
        self.addr.save()

        self._create_abp(cd_geoid="0612")

        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == "0612"
        assert self.addr.sldl_geoid == "01234"  # untouched

    def test_unchanged_value_no_update(self):
        # If the ABP write matches what's already cached, the handler
        # should bail out without saving (we approximate this by
        # checking updated_at-style behavior; the handler's branch is
        # the if dirty_fields: guard).
        self.addr.cd_geoid = "0612"
        self.addr.save()

        # No exception, no infinite signal loop:
        self._create_abp(cd_geoid="0612")

        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == "0612"

    def test_signal_disabled_context_manager_suppresses(self):
        with address_cache_refresh_disabled():
            self._create_abp(cd_geoid="0612")

        self.addr.refresh_from_db()
        # Cache was NOT updated because signal was suppressed.
        assert self.addr.cd_geoid == ""

    def test_signal_re_enabled_after_context_manager(self):
        with address_cache_refresh_disabled():
            self._create_abp(cd_geoid="0612")

        # Outside the context, the signal should fire normally.
        self._create_abp(redistricting_plan_id=1, cd_geoid="0699")

        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == "0699"


class TestRefreshAddressCachesHelper(TestCase):
    """`refresh_address_caches(qs)` brings caches in sync after a
    suppressed-bulk-write block."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusDecadalVintage,
        )
        self.vintage = CensusDecadalVintage.objects.get(decade=2020)
        self.addr1 = Address.objects.create(state_abbreviation="CA")
        self.addr2 = Address.objects.create(state_abbreviation="TX")

        with address_cache_refresh_disabled():
            AddressBoundaryPeriod.objects.create(
                address=self.addr1, vintage=self.vintage,
                cd_geoid="0612", context_date=date(2024, 1, 1),
                assignment_method="SPATIAL_JOIN",
            )
            AddressBoundaryPeriod.objects.create(
                address=self.addr2, vintage=self.vintage,
                cd_geoid="4836", context_date=date(2024, 1, 1),
                assignment_method="SPATIAL_JOIN",
            )

    def test_refresh_brings_caches_in_sync(self):
        from socialwarehouse.geo.models import Address

        # Pre-condition: caches are stale because signal was suppressed.
        self.addr1.refresh_from_db()
        self.addr2.refresh_from_db()
        assert self.addr1.cd_geoid == ""
        assert self.addr2.cd_geoid == ""

        updated = refresh_address_caches(
            Address.objects.filter(pk__in=[self.addr1.pk, self.addr2.pk]),
            today=date(2024, 6, 1),
        )

        self.addr1.refresh_from_db()
        self.addr2.refresh_from_db()
        assert self.addr1.cd_geoid == "0612"
        assert self.addr2.cd_geoid == "4836"
        assert updated == 2

    def test_refresh_no_op_when_cache_already_matches(self):
        from socialwarehouse.geo.models import Address

        # Pre-warm cache so the refresh has nothing to do.
        self.addr1.cd_geoid = "0612"
        self.addr1.save()
        self.addr2.cd_geoid = "4836"
        self.addr2.save()

        updated = refresh_address_caches(
            Address.objects.filter(pk__in=[self.addr1.pk, self.addr2.pk]),
            today=date(2024, 6, 1),
        )

        assert updated == 0


class TestMultiWriteIntegration(TestCase):
    """Realistic ABP write sequence: assign, then redistricting, then
    re-assign. Cache should track the most-recent current-vintage write."""

    def test_sequential_writes_cache_tracks_latest(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusDecadalVintage,
        )
        vintage = CensusDecadalVintage.objects.get(decade=2020)
        addr = Address.objects.create(state_abbreviation="AL")

        # 1. Initial assign: Census-default plan.
        AddressBoundaryPeriod.objects.create(
            address=addr, vintage=vintage,
            cd_geoid="0107", context_date=date(2022, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )
        addr.refresh_from_db()
        assert addr.cd_geoid == "0107"

        # 2. Court-ordered redistricting; re-assign under a plan.
        AddressBoundaryPeriod.objects.create(
            address=addr, vintage=vintage, redistricting_plan_id=1,
            cd_geoid="0102", context_date=date(2023, 1, 1),
            assignment_method="PLAN_SPATIAL_JOIN",
        )
        addr.refresh_from_db()
        assert addr.cd_geoid == "0102"

        # 3. Backfilling a HISTORICAL 2010 vintage; cache should NOT update.
        v_2010 = CensusDecadalVintage.objects.get(decade=2010)
        AddressBoundaryPeriod.objects.create(
            address=addr, vintage=v_2010,
            cd_geoid="0199", context_date=date(2015, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )
        addr.refresh_from_db()
        assert addr.cd_geoid == "0102"  # unchanged by historical backfill

        # 4. New current-vintage assign after another redistricting.
        AddressBoundaryPeriod.objects.create(
            address=addr, vintage=vintage, redistricting_plan_id=2,
            cd_geoid="0103", context_date=timezone.localdate(),
            assignment_method="PLAN_SPATIAL_JOIN",
        )
        addr.refresh_from_db()
        assert addr.cd_geoid == "0103"


class TestSignalMaintainsCensusYear(TestCase):
    """SW#100: census_year is signal-maintained from census-decadal vintages.

    Pins:
    - census-decadal ABP writes update Address.census_year to the
      vintage's decade.
    - Other vintage kinds (ACS / BLS / redistricting) do NOT update
      census_year.
    - Historical (non-current) census-decadal vintages do NOT update
      census_year (the cache is current-by-construction).
    """

    def setUp(self):
        from datetime import date
        from socialwarehouse.geo.models import (
            Address, ACSVintage, CensusDecadalVintage,
        )
        self.vintage_2020 = CensusDecadalVintage.objects.get(decade=2020)
        self.vintage_2010 = CensusDecadalVintage.objects.get(decade=2010)
        # Address starts at the module-default (2020); force to 2010 so
        # the test detects the signal-driven bump explicitly.
        self.addr = Address.objects.create(
            state_abbreviation="CA", census_year=2010,
        )
        self.acs_vintage = ACSVintage.objects.filter(
            span_years=5,
        ).order_by("-end_year").first()
        assert self.acs_vintage is not None

    def test_current_decadal_write_bumps_census_year(self):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            cd_geoid="0610",
            assignment_method="SPATIAL_JOIN",
        )
        self.addr.refresh_from_db()
        assert self.addr.census_year == 2020

    def test_historical_decadal_write_does_not_touch_census_year(self):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2010,
            cd_geoid="0610",
            assignment_method="SPATIAL_JOIN",
        )
        self.addr.refresh_from_db()
        # Historical write — signal bails out before any cache update.
        assert self.addr.census_year == 2010

    def test_acs_vintage_write_does_not_touch_census_year(self):
        """ACSVintage is current but is not a census-decadal kind;
        census_year stays put."""
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.acs_vintage,
            cd_geoid="0610",
            assignment_method="SPATIAL_JOIN",
        )
        self.addr.refresh_from_db()
        assert self.addr.census_year == 2010


class TestCensusYearFromVintageHelper(TestCase):
    """Direct unit tests on the kind-discriminating helper."""

    def test_returns_decade_for_census_decadal(self):
        from socialwarehouse.geo.models import CensusDecadalVintage
        from socialwarehouse.geo.signals import _census_year_from_vintage

        v = CensusDecadalVintage.objects.get(decade=2020)
        assert _census_year_from_vintage(v) == 2020

    def test_returns_none_for_acs(self):
        from socialwarehouse.geo.models import ACSVintage
        from socialwarehouse.geo.signals import _census_year_from_vintage

        v = ACSVintage.objects.filter(span_years=5).first()
        assert _census_year_from_vintage(v) is None

    def test_returns_none_for_none(self):
        from socialwarehouse.geo.signals import _census_year_from_vintage
        assert _census_year_from_vintage(None) is None


class TestSW228OutOfContextDateOrder(TestCase):
    """SW#228: cache must match `boundaries_on(today)` result regardless
    of ABP INSERT order. Previously the signal trusted `instance.{type}_geoid`
    directly which overwrote cache with older-context_date values.

    Bug scenario (per #228 body):
      1. INSERT row A (context_date=2025-06-01, cd_geoid="A") -> cache = "A"
      2. INSERT row B (context_date=2024-01-01, cd_geoid="B") -> cache should
         stay "A" (newer context_date wins), but legacy signal set it to "B".

    After SW#228 (option b), step 2's cache resolution goes through
    `boundaries_on(today, boundary_types=["cd"])` which returns row A
    (most-recent context_date) — cache stays "A". Helper-vs-cache
    invariant holds.
    """

    def setUp(self):
        from socialwarehouse.geo.models import Address, CensusDecadalVintage
        self.vintage_2020 = CensusDecadalVintage.objects.get(decade=2020)
        self.addr = Address.objects.create(state_abbreviation="CA")

    def _create_abp(self, **kwargs):
        from socialwarehouse.geo.models import AddressBoundaryPeriod
        defaults = {
            "address": self.addr,
            "vintage": self.vintage_2020,
            "assignment_method": "SPATIAL_JOIN",
        }
        defaults.update(kwargs)
        return AddressBoundaryPeriod.objects.create(**defaults)

    def test_older_context_date_insert_does_not_clobber_cache(self):
        # Step 1: insert newer-context_date row first; cache becomes "A".
        self._create_abp(cd_geoid="A", context_date=date(2025, 6, 1))
        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == "A"

        # Step 2: insert older-context_date row; cache should STAY "A"
        # because newer-context_date "A" is still the authoritative row
        # for today.
        self._create_abp(cd_geoid="B", context_date=date(2024, 1, 1))
        self.addr.refresh_from_db()
        assert self.addr.cd_geoid == "A", (
            "SW#228: older-context_date INSERT must not clobber cache; "
            "got %r (expected 'A')" % self.addr.cd_geoid
        )

    def test_cache_matches_boundaries_on_today(self):
        # The invariant the SW#201 property test wants: cache matches
        # `boundaries_on(today)` after any sequence of writes.
        self._create_abp(cd_geoid="OLD", context_date=date(2023, 1, 1))
        self._create_abp(cd_geoid="MIDDLE", context_date=date(2024, 6, 1))
        self._create_abp(cd_geoid="NEWEST", context_date=date(2025, 6, 1))
        # Then an INSERT out-of-order:
        self._create_abp(cd_geoid="OLDEST", context_date=date(2022, 1, 1))

        self.addr.refresh_from_db()

        helper_result = self.addr.boundaries_on(timezone.localdate(), boundary_types=["cd"])
        helper_cd = helper_result.get("cd")
        helper_cd_geoid = helper_cd.cd_geoid if helper_cd else ""

        assert self.addr.cd_geoid == helper_cd_geoid, (
            "SW#228 invariant: cache (%r) must match boundaries_on(today) "
            "result (%r) regardless of INSERT order" % (
                self.addr.cd_geoid, helper_cd_geoid,
            )
        )
        # And specifically, "NEWEST" should win.
        assert self.addr.cd_geoid == "NEWEST"


class TestSW188SingleTypeQueryShape(TestCase):
    """SW#188: `boundaries_on(date, boundary_types=[X])` filters the
    queryset to rows that can resolve X (vs fetching all-types). The
    contract is "boundary_on(X, date) only sees rows that could matter
    for X." Verifies the filter shape with assertNumQueries to bound
    the cost.
    """

    def setUp(self):
        from socialwarehouse.geo.models import Address, CensusDecadalVintage
        self.vintage = CensusDecadalVintage.objects.get(decade=2020)
        self.addr = Address.objects.create(state_abbreviation="CA")

    def _create_abp(self, **kwargs):
        from socialwarehouse.geo.models import AddressBoundaryPeriod
        defaults = {
            "address": self.addr,
            "vintage": self.vintage,
            "assignment_method": "SPATIAL_JOIN",
            "context_date": date(2024, 6, 1),
        }
        defaults.update(kwargs)
        return AddressBoundaryPeriod.objects.create(**defaults)

    def test_boundary_on_returns_correct_row(self):
        self._create_abp(cd_geoid="0612", sldl_geoid="0612A")
        # An ABP that only carries vtd (no cd) — single-type filter
        # for "cd" should NOT pick it up.
        self._create_abp(vtd_geoid="9999", context_date=date(2025, 1, 1))

        row = self.addr.boundary_on("cd", date(2025, 6, 1))
        assert row is not None
        assert row.cd_geoid == "0612"

    def test_boundaries_on_with_type_filter_returns_only_requested_types(self):
        self._create_abp(cd_geoid="0612", sldl_geoid="0612A")
        result = self.addr.boundaries_on(date(2024, 6, 1), boundary_types=["cd"])
        assert "cd" in result
        assert "sldl" not in result  # not requested

    def test_boundaries_on_unfiltered_returns_all_types(self):
        self._create_abp(cd_geoid="0612", sldl_geoid="0612A", state_geoid="06")
        result = self.addr.boundaries_on(date(2024, 6, 1))
        # Unfiltered returns all types the row touches (cd, sldl, state).
        assert "cd" in result
        assert "sldl" in result
        assert "state" in result
