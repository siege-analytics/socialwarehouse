"""Tests for Template-readiness C medium-priority batch (SW#191):
Address + ABP carry cache fields for PUMA, UrbanArea, and 7 per-kind
special districts. Signal-propagation covers them automatically via
Address._BOUNDARY_TYPES membership.
"""

from datetime import date

from django.test import TestCase


C_MEDIUM_TYPES = [
    "puma", "urban_area",
    "fire_district", "water_district", "hospital_district",
    "library_district", "cemetery_district", "mosquito_district",
    "other_special_district",
]


class TestAddressCMediumFields(TestCase):

    def test_all_fields_default_empty(self):
        from socialwarehouse.geo.models import Address

        addr = Address.objects.create(state_abbreviation="CA")
        for btype in C_MEDIUM_TYPES:
            assert getattr(addr, f"{btype}_geoid") == ""

    def test_realistic_values_round_trip(self):
        from socialwarehouse.geo.models import Address

        addr = Address.objects.create(
            state_abbreviation="CA",
            puma_geoid="0603701",       # state 06 + PUMA 03701
            urban_area_geoid="51445",   # Census UA code
            fire_district_geoid="0612345",
            water_district_geoid="0654321",
            hospital_district_geoid="0613579",
            library_district_geoid="0624680",
            cemetery_district_geoid="0698765",
            mosquito_district_geoid="0611111",
            other_special_district_geoid="0699999",
        )
        addr.refresh_from_db()
        assert addr.puma_geoid == "0603701"
        assert addr.urban_area_geoid == "51445"
        assert addr.fire_district_geoid == "0612345"
        assert addr.water_district_geoid == "0654321"
        assert addr.hospital_district_geoid == "0613579"
        assert addr.library_district_geoid == "0624680"
        assert addr.cemetery_district_geoid == "0698765"
        assert addr.mosquito_district_geoid == "0611111"
        assert addr.other_special_district_geoid == "0699999"


class TestCMediumBoundaryTypesCoverage(TestCase):

    def test_all_in_boundary_types_tuple(self):
        from socialwarehouse.geo.models import Address

        for btype in C_MEDIUM_TYPES:
            assert btype in Address._BOUNDARY_TYPES, f"{btype} missing"

    def test_f11_helpers_recognize_each_type(self):
        from socialwarehouse.geo.models import Address

        addr = Address.objects.create(state_abbreviation="NY")
        for btype in C_MEDIUM_TYPES:
            # All return empty / None for an address with no ABP rows.
            assert list(addr.boundary_history(boundary_type=btype)) == []
            assert addr.boundary_on(btype, date(2024, 6, 1)) is None
            assert addr.geoid_on(btype, date(2024, 6, 1)) is None
            assert addr.boundary_timeline(btype) == []


class TestSignalPropagationCMedium(TestCase):

    def test_signal_updates_c_medium_cache_fields(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusDecadalVintage,
        )

        addr = Address.objects.create(state_abbreviation="CA")
        vintage = CensusDecadalVintage.objects.get(decade=2020)

        AddressBoundaryPeriod.objects.create(
            address=addr,
            vintage=vintage,
            puma_geoid="0603701",
            fire_district_geoid="0612345",
            context_date=date(2024, 6, 1),
            assignment_method="SPATIAL_JOIN",
        )

        addr.refresh_from_db()
        # vintage_2020 is current; the F11 step-2b signal should refresh the cache.
        assert addr.puma_geoid == "0603701"
        assert addr.fire_district_geoid == "0612345"
        # Unset C-medium fields stay empty.
        assert addr.water_district_geoid == ""
        assert addr.library_district_geoid == ""
