"""Tests for SW#198: Address.is_redistricting_assignment_stale.

Pins the documented semantic: "current plan = the plan that would
apply if an election were held at the time of this call,"
resolved via RedistrictingPlan.objects.for_date.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class _StaleBase(TestCase):

    def setUp(self):
        from socialwarehouse.geo.models import Address, CensusDecadalVintage

        self.vintage = CensusDecadalVintage.objects.get(decade=2020)
        self.addr = Address.objects.create(
            state_abbreviation="CA",
            state_geoid="06",
        )

    def _make_plan(self, *, state_fips, chamber, effective_from,
                   effective_to=None, plan_name="test plan"):
        from siege_utilities.geo.django.models import RedistrictingPlan

        return RedistrictingPlan.objects.create(
            state_fips=state_fips,
            chamber=chamber,
            cycle_year=2020,
            plan_name=plan_name,
            effective_from=effective_from,
            effective_to=effective_to,
        )

    def _make_abp(self, *, boundary_type, plan_id, geoid="0612", context_date=None):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        kwargs = {
            "address": self.addr,
            "vintage": self.vintage,
            "redistricting_plan_id": plan_id,
            "context_date": context_date or date(2024, 1, 1),
            "assignment_method": "SPATIAL_JOIN",
        }
        kwargs[f"{boundary_type}_geoid"] = geoid
        return AddressBoundaryPeriod.objects.create(**kwargs)


class TestNonRedistrictingTypesAlwaysNotStale(_StaleBase):
    """state, county, etc. aren't redistricted; predicate is False."""

    def test_state_is_not_stale(self):
        assert self.addr.is_redistricting_assignment_stale("state") is False

    def test_county_is_not_stale(self):
        assert self.addr.is_redistricting_assignment_stale("county") is False

    def test_zcta_is_not_stale(self):
        assert self.addr.is_redistricting_assignment_stale("zcta") is False


class TestUnknownBoundaryTypeRaises(_StaleBase):

    def test_raises(self):
        with self.assertRaises(ValueError):
            self.addr.is_redistricting_assignment_stale("not-a-real-type")


class TestNoStateGeoidNotStale(_StaleBase):

    def test_empty_state_geoid_returns_false(self):
        # Address without a cached state — can't know which state's plans
        # to check.
        self.addr.state_geoid = ""
        self.addr.save()
        assert self.addr.is_redistricting_assignment_stale("cd") is False


class TestNoCurrentPlanNotStale(_StaleBase):
    """When no RedistrictingPlan is "in effect today" for the state,
    the predicate returns False (silence > alarm-without-information).
    """

    def test_no_plan_in_db(self):
        self._make_abp(boundary_type="cd", plan_id=None)
        assert self.addr.is_redistricting_assignment_stale("cd") is False

    def test_only_future_plan(self):
        # A plan exists but its effective_from is after today.
        self._make_plan(
            state_fips="06", chamber="congress",
            effective_from=date(2099, 1, 1),
        )
        self._make_abp(boundary_type="cd", plan_id=None)
        assert self.addr.is_redistricting_assignment_stale("cd") is False


class TestNoABPNotStale(_StaleBase):
    """If the address has no ABP for this type, nothing is stale."""

    def test_no_abp(self):
        self._make_plan(
            state_fips="06", chamber="congress",
            effective_from=date(2022, 1, 1),
        )
        assert self.addr.is_redistricting_assignment_stale("cd") is False


class TestStaleWhenPlanMismatches(_StaleBase):

    def test_abp_under_older_plan_is_stale(self):
        # Older plan: enacted 2022-01-01, superseded 2024-01-01.
        old_plan = self._make_plan(
            state_fips="06", chamber="congress",
            effective_from=date(2022, 1, 1),
            effective_to=date(2024, 1, 1),
            plan_name="old",
        )
        # Newer plan: enacted 2024-01-02, still in effect.
        new_plan = self._make_plan(
            state_fips="06", chamber="congress",
            effective_from=date(2024, 1, 2),
            plan_name="new",
        )
        # ABP was assigned under the old plan.
        self._make_abp(boundary_type="cd", plan_id=old_plan.id)

        with patch.object(timezone, "localdate", return_value=date(2026, 5, 20)):
            assert self.addr.is_redistricting_assignment_stale("cd") is True

    def test_abp_with_null_plan_and_current_plan_exists_is_stale(self):
        # Census-default ABP (no plan), but a plan is currently in effect
        # — the cache is older than the plan record.
        self._make_plan(
            state_fips="06", chamber="congress",
            effective_from=date(2022, 1, 1),
        )
        self._make_abp(boundary_type="cd", plan_id=None)

        with patch.object(timezone, "localdate", return_value=date(2026, 5, 20)):
            assert self.addr.is_redistricting_assignment_stale("cd") is True


class TestNotStaleWhenPlansMatch(_StaleBase):

    def test_abp_under_current_plan_not_stale(self):
        current = self._make_plan(
            state_fips="06", chamber="congress",
            effective_from=date(2022, 1, 1),
        )
        self._make_abp(boundary_type="cd", plan_id=current.id)

        with patch.object(timezone, "localdate", return_value=date(2026, 5, 20)):
            assert self.addr.is_redistricting_assignment_stale("cd") is False


class TestStateSenateAndHouseChambers(_StaleBase):

    def test_sldl_uses_state_house_chamber(self):
        # Plan for state_house chamber → matches sldl checks.
        house = self._make_plan(
            state_fips="06", chamber="state_house",
            effective_from=date(2022, 1, 1),
        )
        # ABP under a different plan id → stale.
        self._make_abp(boundary_type="sldl", plan_id=9999)

        with patch.object(timezone, "localdate", return_value=date(2026, 5, 20)):
            assert self.addr.is_redistricting_assignment_stale("sldl") is True

    def test_sldu_uses_state_senate_chamber(self):
        senate = self._make_plan(
            state_fips="06", chamber="state_senate",
            effective_from=date(2022, 1, 1),
        )
        self._make_abp(boundary_type="sldu", plan_id=senate.id)

        with patch.object(timezone, "localdate", return_value=date(2026, 5, 20)):
            assert self.addr.is_redistricting_assignment_stale("sldu") is False
