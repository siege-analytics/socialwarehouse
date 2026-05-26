from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.test import TestCase

from socialwarehouse.geo.models import PrecinctVTDIntersection


@pytest.mark.django_db
class TestPrecinctVTDIntersection(TestCase):
    def test_create_intersection(self):
        pvtd = PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
            overlap_area_sqm=500000,
            overlap_fraction=Decimal("0.7500"),
            is_dominant=True,
        )
        assert pvtd.precinct_geoid == "4801234"
        assert pvtd.vtd_geoid == "48001000100"
        assert pvtd.election_cycle == 2024
        assert pvtd.is_dominant is True
        assert pvtd.computed_at is not None

    def test_unique_constraint(self):
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
        )
        with pytest.raises(IntegrityError):
            PrecinctVTDIntersection.objects.create(
                precinct_geoid="4801234",
                vtd_geoid="48001000100",
                election_cycle=2024,
                state="TX",
            )

    def test_same_precinct_different_vtds(self):
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
            overlap_fraction=Decimal("0.6000"),
            is_dominant=True,
        )
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000200",
            election_cycle=2024,
            state="TX",
            overlap_fraction=Decimal("0.4000"),
            is_dominant=False,
        )
        assert PrecinctVTDIntersection.objects.filter(
            precinct_geoid="4801234", election_cycle=2024,
        ).count() == 2

    def test_same_vtd_different_precincts(self):
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
        )
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4805678",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
        )
        assert PrecinctVTDIntersection.objects.filter(
            vtd_geoid="48001000100", election_cycle=2024,
        ).count() == 2

    def test_different_cycles(self):
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2022,
            state="TX",
        )
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
        )
        assert PrecinctVTDIntersection.objects.filter(
            precinct_geoid="4801234",
        ).count() == 2

    def test_str(self):
        pvtd = PrecinctVTDIntersection(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
            overlap_fraction=Decimal("0.7500"),
        )
        s = str(pvtd)
        assert "4801234" in s
        assert "48001000100" in s

    def test_filter_by_state_and_cycle(self):
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
        )
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="0101234",
            vtd_geoid="01001000100",
            election_cycle=2024,
            state="AL",
        )
        tx = PrecinctVTDIntersection.objects.filter(
            state="TX", election_cycle=2024,
        )
        assert tx.count() == 1

    def test_dominant_filter(self):
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000100",
            election_cycle=2024,
            state="TX",
            overlap_fraction=Decimal("0.6000"),
            is_dominant=True,
        )
        PrecinctVTDIntersection.objects.create(
            precinct_geoid="4801234",
            vtd_geoid="48001000200",
            election_cycle=2024,
            state="TX",
            overlap_fraction=Decimal("0.4000"),
            is_dominant=False,
        )
        dominant = PrecinctVTDIntersection.objects.filter(
            precinct_geoid="4801234",
            election_cycle=2024,
            is_dominant=True,
        )
        assert dominant.count() == 1
        assert dominant.first().vtd_geoid == "48001000100"


@pytest.mark.django_db
class TestDeltaSchemaRegistration(TestCase):
    def test_redistricting_plans_registered(self):
        from socialwarehouse.delta.tables import TABLES
        assert "silver.redistricting_plans" in TABLES
        entry = TABLES["silver.redistricting_plans"]
        assert "state" in entry["partition_by"]

    def test_address_boundary_periods_registered(self):
        from socialwarehouse.delta.tables import TABLES
        assert "silver.address_boundary_periods" in TABLES
        entry = TABLES["silver.address_boundary_periods"]
        assert "state_abbreviation" in entry["partition_by"]

    def test_precinct_vtd_intersections_registered(self):
        from socialwarehouse.delta.tables import TABLES
        assert "silver.precinct_vtd_intersections" in TABLES
        entry = TABLES["silver.precinct_vtd_intersections"]
        assert "state" in entry["partition_by"]
        assert "election_cycle" in entry["partition_by"]

    def test_redistricting_plans_schema_fields(self):
        from socialwarehouse.delta.tables import SILVER_REDISTRICTING_PLANS
        field_names = [f.name for f in SILVER_REDISTRICTING_PLANS.fields]
        assert "plan_uuid" in field_names
        assert "state" in field_names
        assert "chamber" in field_names
        assert "effective_from" in field_names
        assert "effective_to" in field_names

    def test_abp_schema_fields(self):
        from socialwarehouse.delta.tables import SILVER_ADDRESS_BOUNDARY_PERIODS
        field_names = [f.name for f in SILVER_ADDRESS_BOUNDARY_PERIODS.fields]
        assert "address_id" in field_names
        assert "redistricting_plan_id" in field_names
        assert "context_date" in field_names
        assert "cd_geoid" in field_names
        assert "assignment_method" in field_names

    def test_pvtd_schema_fields(self):
        from socialwarehouse.delta.tables import SILVER_PRECINCT_VTD_INTERSECTIONS
        field_names = [f.name for f in SILVER_PRECINCT_VTD_INTERSECTIONS.fields]
        assert "precinct_geoid" in field_names
        assert "vtd_geoid" in field_names
        assert "election_cycle" in field_names
        assert "overlap_fraction" in field_names
