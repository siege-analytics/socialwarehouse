"""Tests for SW#200: the address_boundary_cache_changed cascade signal.

Pins the contract: signal fires after F11 step-2b updates cache, with
the documented kwargs. Doesn't ship a subscriber — the FEC analysis
project (or whoever surfaces first) ships theirs.
"""

from datetime import date

from django.dispatch import receiver
from django.test import TestCase

from socialwarehouse.geo.signals import (
    address_boundary_cache_changed,
    address_cache_refresh_disabled,
    refresh_address_caches,
)


class _CaptureBase(TestCase):
    """Subscribe to the cascade signal and stash received kwargs for
    assertions; cleanly disconnect on teardown."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, CensusDecadalVintage,
        )
        self.vintage = CensusDecadalVintage.objects.get(decade=2020)
        self.addr = Address.objects.create(state_abbreviation="CA")
        self._received = []

        @receiver(address_boundary_cache_changed, weak=False,
                  dispatch_uid="test_cache_change_signal_capture")
        def _capture(sender, instance, dirty_fields, source_abp, **kw):
            self._received.append({
                "sender": sender,
                "instance": instance,
                "dirty_fields": list(dirty_fields),
                "source_abp": source_abp,
            })

        self._capture = _capture

    def tearDown(self):
        address_boundary_cache_changed.disconnect(
            self._capture,
            dispatch_uid="test_cache_change_signal_capture",
        )


class TestSignalFiresOnCurrentVintageWrite(_CaptureBase):

    def test_fires_with_documented_kwargs(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod,
        )

        abp = AddressBoundaryPeriod.objects.create(
            address=self.addr, vintage=self.vintage,
            cd_geoid="0612", assignment_method="SPATIAL_JOIN",
        )

        assert len(self._received) == 1
        event = self._received[0]
        assert event["sender"] is Address
        assert event["instance"].pk == self.addr.pk
        assert "cd_geoid" in event["dirty_fields"]
        assert event["source_abp"].pk == abp.pk


class TestSignalDoesNotFireForBackfill(_CaptureBase):
    """No cache update → no signal."""

    def test_historical_vintage_does_not_fire(self):
        from socialwarehouse.geo.models import (
            AddressBoundaryPeriod, CensusDecadalVintage,
        )
        old = CensusDecadalVintage.objects.get(decade=2010)
        AddressBoundaryPeriod.objects.create(
            address=self.addr, vintage=old,
            cd_geoid="0107", context_date=date(2015, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )
        assert self._received == []

    def test_no_change_does_not_fire(self):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        # Pre-populate the cache.
        self.addr.cd_geoid = "0612"
        self.addr.save()

        # ABP write that matches the cache → no dirty_fields → no signal.
        AddressBoundaryPeriod.objects.create(
            address=self.addr, vintage=self.vintage,
            cd_geoid="0612", assignment_method="SPATIAL_JOIN",
        )
        assert self._received == []


class TestSignalFiresFromBulkHelper(_CaptureBase):

    def test_bulk_refresh_fires_with_source_abp_none(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod,
        )

        with address_cache_refresh_disabled():
            AddressBoundaryPeriod.objects.create(
                address=self.addr, vintage=self.vintage,
                cd_geoid="0612", context_date=date(2024, 1, 1),
                assignment_method="SPATIAL_JOIN",
            )
        # Per-write signal suppressed — nothing received yet.
        assert self._received == []

        refresh_address_caches(
            Address.objects.filter(pk=self.addr.pk),
            today=date(2024, 6, 1),
        )

        assert len(self._received) == 1
        event = self._received[0]
        assert event["instance"].pk == self.addr.pk
        assert "cd_geoid" in event["dirty_fields"]
        # source_abp=None signals "bulk path, not a single triggering write."
        assert event["source_abp"] is None
