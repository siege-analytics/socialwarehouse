"""Unit tests for socialwarehouse.geo models."""

import pytest
from django.test import TestCase


class TestAddressModel(TestCase):
    """Test Address model creation and methods."""

    def test_create_address(self):
        from socialwarehouse.geo.models import Address

        addr = Address(
            primary_number="123",
            street_name="Main",
            street_suffix="St",
            city_name="Springfield",
            state_abbreviation="IL",
            zip5="62701",
        )
        assert str(addr) == "123 Main St"

    def test_assign_census_units_from_fips(self):
        from socialwarehouse.geo.models import Address

        addr = Address()
        addr.assign_census_units_from_fips(
            state_fips="11",
            county_fips="001",
            tract="006202",
            block="1031",
        )
        assert addr.state_geoid == "11"
        assert addr.county_geoid == "11001"
        assert addr.tract_geoid == "11001006202"
        assert addr.block_group_geoid == "110010062021"
        assert addr.block_geoid == "110010062021031"

    def test_assign_census_units_from_fips_partial(self):
        from socialwarehouse.geo.models import Address

        addr = Address()
        addr.assign_census_units_from_fips(
            state_fips="06",
            county_fips="037",
            tract=None,
            block=None,
        )
        assert addr.state_geoid == "06"
        assert addr.county_geoid == "06037"
        # Post-F3/SW#92: CharField default is "" not None.
        assert addr.tract_geoid == ""

    def test_backwards_compat_alias(self):
        from socialwarehouse.geo.models import United_States_Address, Address

        assert United_States_Address is Address


class TestCensusDecadalVintageManager(TestCase):
    """Test the for_year manager method preserved from CensusVintageConfig.

    The seed of 2010/2020 decadal vintages is performed by migration 0004
    (seed_known_vintages); these tests verify the lookup against that
    seeded state.
    """

    def test_for_year_2018_returns_2010_decade(self):
        from socialwarehouse.geo.models import CensusDecadalVintage

        v = CensusDecadalVintage.objects.for_year(2018)
        assert v is not None
        assert v.decade == 2010

    def test_for_year_2022_returns_2020_decade(self):
        from socialwarehouse.geo.models import CensusDecadalVintage

        v = CensusDecadalVintage.objects.for_year(2022)
        assert v is not None
        assert v.decade == 2020

    def test_for_year_before_seeded_decades_returns_none(self):
        from socialwarehouse.geo.models import CensusDecadalVintage

        # 1995 → decade 1990, not seeded.
        v = CensusDecadalVintage.objects.for_year(1995)
        assert v is None


class TestAddressBoundaryPeriod(TestCase):
    """Test AddressBoundaryPeriod model against the polymorphic Vintage."""

    def test_create_boundary_period(self):
        from socialwarehouse.geo.models import Address, AddressBoundaryPeriod, CensusDecadalVintage

        vintage = CensusDecadalVintage.objects.get(decade=2020)

        addr = Address.objects.create(
            primary_number="456",
            street_name="Oak",
            street_suffix="Ave",
            state_abbreviation="CA",
        )

        abp = AddressBoundaryPeriod.objects.create(
            address=addr,
            vintage=vintage,
            state_geoid="06",
            county_geoid="06037",
            cd_geoid="0634",
            assignment_method="SPATIAL_JOIN",
        )

        # __str__ uses Vintage.__str__ which is "kind:name".
        assert f"Address {addr.pk}" in str(abp)
        assert "census-decadal:2020" in str(abp)
        assert abp.cd_geoid == "0634"

    def test_unique_together(self):
        from django.db import IntegrityError
        from socialwarehouse.geo.models import Address, AddressBoundaryPeriod, CensusDecadalVintage

        vintage = CensusDecadalVintage.objects.get(decade=2020)
        addr = Address.objects.create(state_abbreviation="TX")

        AddressBoundaryPeriod.objects.create(address=addr, vintage=vintage)

        with pytest.raises(IntegrityError):
            AddressBoundaryPeriod.objects.create(address=addr, vintage=vintage)


class TestPoliticalModels(TestCase):
    """Test political extension models can be created."""

    def test_political_state_str(self):
        from socialwarehouse.geo.models import PoliticalState

        # Can't create without siege_geo State, but can test the model exists
        assert PoliticalState._meta.db_table == "sw_political_state"

    def test_political_cd_str(self):
        from socialwarehouse.geo.models import PoliticalCongressionalDistrict

        assert PoliticalCongressionalDistrict._meta.db_table == "sw_political_cd"


class TestIntersectionModels(TestCase):
    """Test intersection model metadata."""

    def test_county_cd_table_name(self):
        from socialwarehouse.geo.models import CountyCongressionalDistrictIntersection

        assert CountyCongressionalDistrictIntersection._meta.db_table == "sw_geo_intersection_county_cd"

    def test_vtd_cd_table_name(self):
        from socialwarehouse.geo.models import VTDCongressionalDistrictIntersection

        assert VTDCongressionalDistrictIntersection._meta.db_table == "sw_geo_intersection_vtd_cd"
