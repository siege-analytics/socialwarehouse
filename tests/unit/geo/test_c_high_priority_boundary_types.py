"""Tests for Template-readiness C high-priority batch (SW#191):
Address and ABP carry cache fields for ZCTA, Place, CBSA, and
SchoolDistrict; F11 helpers cover the new types automatically.

The boundary models themselves live in siege_utilities (SU#532);
these tests cover the SW-side cache contract only.
"""

from datetime import date

from django.test import TestCase


class TestAddressNewGeoidFields(TestCase):
    """Address has the four new cache fields with the documented max_lengths."""

    def test_all_four_fields_default_to_empty_string(self):
        from socialwarehouse.geo.models import Address

        addr = Address.objects.create(state_abbreviation="TX")
        assert addr.zcta_geoid == ""
        assert addr.place_geoid == ""
        assert addr.cbsa_geoid == ""
        assert addr.school_district_geoid == ""

    def test_fields_accept_realistic_values(self):
        from socialwarehouse.geo.models import Address

        addr = Address.objects.create(
            state_abbreviation="IL",
            zcta_geoid="60601",        # Chicago downtown ZCTA
            place_geoid="1714000",     # Chicago place GEOID (state 17 + place 14000)
            cbsa_geoid="16980",        # Chicago-Naperville-Elgin CBSA
            school_district_geoid="1709930",  # Chicago Public Schools LEAID
        )
        addr.refresh_from_db()
        assert addr.zcta_geoid == "60601"
        assert addr.place_geoid == "1714000"
        assert addr.cbsa_geoid == "16980"
        assert addr.school_district_geoid == "1709930"


class TestBoundaryTypesCoverage(TestCase):
    """The four new types appear in `Address._BOUNDARY_TYPES`."""

    def test_new_types_are_in_boundary_types_tuple(self):
        from socialwarehouse.geo.models import Address

        for btype in ("zcta", "place", "cbsa", "school_district"):
            assert btype in Address._BOUNDARY_TYPES, (
                f"{btype} missing from Address._BOUNDARY_TYPES"
            )

    def test_f11_helpers_recognize_new_types_without_raising(self):
        from socialwarehouse.geo.models import Address

        addr = Address.objects.create(state_abbreviation="NY")
        # Should not raise; returns empty queryset/dict for an address
        # with no ABP rows.
        assert list(addr.boundary_history(boundary_type="zcta")) == []
        assert addr.boundary_on("place", date(2024, 6, 1)) is None
        assert addr.geoid_on("cbsa", date(2024, 6, 1)) is None
        assert addr.boundary_timeline("school_district") == []


class TestABPNewGeoidFields(TestCase):
    """AddressBoundaryPeriod has the four new geoid columns."""

    def test_abp_can_carry_new_geoids(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusDecadalVintage,
        )

        addr = Address.objects.create(state_abbreviation="IL")
        vintage = CensusDecadalVintage.objects.get(decade=2020)

        abp = AddressBoundaryPeriod.objects.create(
            address=addr,
            vintage=vintage,
            zcta_geoid="60601",
            place_geoid="1714000",
            cbsa_geoid="16980",
            school_district_geoid="1709930",
            context_date=date(2024, 6, 1),
            assignment_method="SPATIAL_JOIN",
        )

        abp.refresh_from_db()
        assert abp.zcta_geoid == "60601"
        assert abp.place_geoid == "1714000"
        assert abp.cbsa_geoid == "16980"
        assert abp.school_district_geoid == "1709930"

    def test_step_2b_signal_propagates_new_geoids_to_address_cache(self):
        """The F11 step-2b signal should refresh the new cache fields too,
        since they're members of Address._BOUNDARY_TYPES.
        """
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusDecadalVintage,
        )

        addr = Address.objects.create(state_abbreviation="IL")
        vintage = CensusDecadalVintage.objects.get(decade=2020)

        AddressBoundaryPeriod.objects.create(
            address=addr,
            vintage=vintage,
            zcta_geoid="60601",
            cbsa_geoid="16980",
            context_date=date(2024, 6, 1),
            assignment_method="SPATIAL_JOIN",
        )

        addr.refresh_from_db()
        # The signal short-circuits if vintage isn't current; vintage_2020
        # is current as of today (effective_to=None), so cache updates.
        assert addr.zcta_geoid == "60601"
        assert addr.cbsa_geoid == "16980"
        # place / school_district were not set on the ABP row; cache stays empty.
        assert addr.place_geoid == ""
        assert addr.school_district_geoid == ""
