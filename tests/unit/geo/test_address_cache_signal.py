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
