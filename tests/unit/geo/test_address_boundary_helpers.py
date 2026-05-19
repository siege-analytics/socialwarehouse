"""Tests for F11 (SW#100) step-2 helpers: Address.boundary_history /
boundaries_on / current_boundaries.

The helpers expose ``AddressBoundaryPeriod`` as the authoritative source
for "which boundaries did this address belong to on date X" and "every
boundary this address has ever been in." See
docs/designs/f11-address-temporal-boundary-history.md for the design.

Coverage scope:
    - boundary_history (with and without boundary_type filter).
    - boundaries_on falling back to the NULL-plan (Census default) row
      when no plan-bound row covers the date.
    - current_boundaries delegating to today's date.

Out of scope (deferred to integration tests):
    - boundaries_on resolving a plan-bound row by RedistrictingPlan's
      effective_from / effective_to. Requires real siege_utilities
      RedistrictingPlan rows; those tests live with assign_boundaries.
"""

from datetime import date

from django.test import TestCase


class TestBoundaryHistory(TestCase):
    """Address.boundary_history: every recorded assignment."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )

        CensusVintageConfig.seed_defaults()
        self.vintage_2020 = CensusVintageConfig.objects.get(decade=2020)
        self.vintage_2010 = CensusVintageConfig.objects.get(decade=2010)

        self.addr = Address.objects.create(
            primary_number="100",
            street_name="Main",
            state_abbreviation="AL",
        )

        # Three periods: 2010 default, 2020 default, 2020 "Milligan" plan.
        self.abp_2010 = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2010,
            state_geoid="01",
            county_geoid="01073",
            cd_geoid="0107",
            context_date=date(2015, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )
        self.abp_2020_default = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            state_geoid="01",
            county_geoid="01073",
            cd_geoid="0107",
            context_date=date(2022, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )
        self.abp_2020_plan = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            redistricting_plan_id=42,  # db_constraint=False; bare FK ID is fine
            state_geoid="01",
            county_geoid="01073",
            cd_geoid="0102",
            context_date=date(2024, 1, 1),
            assignment_method="PLAN_SPATIAL_JOIN",
        )

    def test_returns_all_periods_for_address(self):
        history = list(self.addr.boundary_history())
        assert len(history) == 3
        # Most-recent-first ordering.
        assert history[0] == self.abp_2020_plan
        assert history[-1] == self.abp_2010

    def test_filter_by_boundary_type_keeps_rows_with_geoid(self):
        cd_history = list(self.addr.boundary_history(boundary_type="cd"))
        assert len(cd_history) == 3  # all three rows have cd_geoid populated
        geoids = {p.cd_geoid for p in cd_history}
        assert geoids == {"0107", "0102"}

    def test_filter_by_boundary_type_drops_rows_without_geoid(self):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        # A row with no sldl_geoid should be excluded by sldl filter.
        sldl_history = list(self.addr.boundary_history(boundary_type="sldl"))
        assert sldl_history == []

        # Add an sldl-bearing row; now the filter should pick it up.
        AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            redistricting_plan_id=99,
            sldl_geoid="01-005",
            context_date=date(2024, 6, 1),
            assignment_method="PLAN_SPATIAL_JOIN",
        )
        sldl_history = list(self.addr.boundary_history(boundary_type="sldl"))
        assert len(sldl_history) == 1
        assert sldl_history[0].sldl_geoid == "01-005"

    def test_unknown_boundary_type_raises(self):
        import pytest

        with pytest.raises(ValueError) as exc:
            self.addr.boundary_history(boundary_type="precinct")
        assert "precinct" in str(exc.value)

    def test_isolation_between_addresses(self):
        from socialwarehouse.geo.models import Address

        other = Address.objects.create(state_abbreviation="CA")
        assert list(other.boundary_history()) == []
        # And the original address is unaffected.
        assert len(list(self.addr.boundary_history())) == 3


class TestBoundariesOnNullPlanFallback(TestCase):
    """boundaries_on falls back to NULL-plan (Census default) rows when no
    plan-bound row covers the date.

    Plan-bound resolution (using RedistrictingPlan.effective_from /
    effective_to) is covered by integration tests; this unit test
    exercises the static-boundary / Census-default path that doesn't
    require any RedistrictingPlan rows."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )

        CensusVintageConfig.seed_defaults()
        self.vintage_2020 = CensusVintageConfig.objects.get(decade=2020)

        self.addr = Address.objects.create(state_abbreviation="TX")

        # A NULL-plan row carrying static-boundary geoids only.
        self.abp_default = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            redistricting_plan=None,
            state_geoid="48",
            county_geoid="48201",
            tract_geoid="48201100000",
            context_date=date(2022, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )

    def test_returns_default_row_for_static_boundary_types(self):
        result = self.addr.boundaries_on(date(2023, 6, 15))
        assert result["state"] == self.abp_default
        assert result["county"] == self.abp_default
        assert result["tract"] == self.abp_default

    def test_omits_types_with_no_geoid(self):
        # No cd_geoid was set on the default row, so cd should not appear.
        result = self.addr.boundaries_on(date(2023, 6, 15))
        assert "cd" not in result
        assert "sldl" not in result

    def test_no_vintage_for_year_returns_empty(self):
        # Year with no CensusVintageConfig row (seed_defaults covers 2010/2020).
        result = self.addr.boundaries_on(date(1985, 1, 1))
        assert result == {}


class TestCurrentBoundaries(TestCase):
    """current_boundaries delegates to boundaries_on(today)."""

    def test_delegates_to_today(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )
        from django.utils import timezone

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)
        addr = Address.objects.create(state_abbreviation="NY")

        abp = AddressBoundaryPeriod.objects.create(
            address=addr,
            vintage=vintage,
            state_geoid="36",
            county_geoid="36061",
            context_date=timezone.localdate(),
            assignment_method="SPATIAL_JOIN",
        )

        current = addr.current_boundaries()
        assert current["state"] == abp
        assert current["county"] == abp
