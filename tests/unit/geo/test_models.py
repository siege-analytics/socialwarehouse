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
        assert addr.tract_geoid is None

    def test_backwards_compat_alias(self):
        from socialwarehouse.geo.models import United_States_Address, Address

        assert United_States_Address is Address


class TestCensusVintageConfig(TestCase):
    """Test CensusVintageConfig model."""

    def test_seed_defaults(self):
        from socialwarehouse.geo.models import CensusVintageConfig

        created = CensusVintageConfig.seed_defaults()
        assert created == 4
        # Idempotent
        created_again = CensusVintageConfig.seed_defaults()
        assert created_again == 0

    def test_for_year(self):
        from socialwarehouse.geo.models import CensusVintageConfig

        CensusVintageConfig.seed_defaults()

        v2018 = CensusVintageConfig.for_year(2018)
        assert v2018 is not None
        assert v2018.decade == 2010

        v2022 = CensusVintageConfig.for_year(2022)
        assert v2022 is not None
        assert v2022.decade == 2020

        # 1990 is not active by default
        v1995 = CensusVintageConfig.for_year(1995)
        assert v1995 is None

    def test_str(self):
        from socialwarehouse.geo.models import CensusVintageConfig

        CensusVintageConfig.seed_defaults()
        v = CensusVintageConfig.objects.get(decade=2020)
        assert "2020" in str(v)
        assert "2029" in str(v)


class TestAddressBoundaryPeriod(TestCase):
    """Test AddressBoundaryPeriod model."""

    def test_create_boundary_period(self):
        from socialwarehouse.geo.models import Address, AddressBoundaryPeriod, CensusVintageConfig

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)

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

        assert str(abp) == f"Address {addr.pk} @ 2020 Census"
        assert abp.cd_geoid == "0634"

    def test_unique_together(self):
        from django.db import IntegrityError
        from socialwarehouse.geo.models import Address, AddressBoundaryPeriod, CensusVintageConfig

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)
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
