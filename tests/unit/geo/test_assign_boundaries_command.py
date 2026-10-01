"""End-to-end tests for the ``assign_boundaries`` management command.

Two things the command has to get right against the siege_utilities
boundary models:

- Spatial lookups go through the boundary models' ``geometry`` field.
  Any other field name raises a FieldError inside the per-address
  ``try``, which the command logs and counts as a failure, so every
  address ends up unassigned.
- In plan-aware mode, ``--state`` is a state abbreviation (``--state AL``,
  the same value the Address queryset filters on), and
  ``_fetch_active_plans`` must resolve it to that state's active plans.
  Otherwise the plan is never found and the Census-drawn districts are
  used instead of the court-ordered ones.
"""

from datetime import date
from io import StringIO

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management import call_command
from django.test import TestCase


def _box(min_x, min_y, max_x, max_y):
    return MultiPolygon(
        Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y))),
        srid=4326,
    )


# Alabama-shaped stand-in; the test address sits in the west half.
AL_BOX = _box(-88.0, 30.0, -85.0, 35.0)
WEST_HALF = _box(-88.0, 30.0, -86.5, 35.0)
EAST_HALF = _box(-86.5, 30.0, -85.0, 35.0)


class _AssignBoundariesBase(TestCase):

    def setUp(self):
        from siege_utilities.geo.django.models import (
            CongressionalDistrict,
            County,
            RedistrictingPlan,
            State,
        )

        from socialwarehouse.geo.models import Address

        self.state = State.objects.create(
            feature_id="01", name="Alabama", vintage_year=2020,
            geoid="01", state_fips="01", abbreviation="AL", geometry=AL_BOX,
        )
        County.objects.create(
            feature_id="01073", name="Jefferson", vintage_year=2020,
            geoid="01073", state_fips="01", state=self.state, county_fips="073",
            geometry=WEST_HALF,
        )
        CongressionalDistrict.objects.create(
            feature_id="0107", name="Congressional District 7", vintage_year=2020,
            geoid="0107", state_fips="01", state=self.state, district_number="07",
            geometry=WEST_HALF,
        )
        CongressionalDistrict.objects.create(
            feature_id="0102", name="Congressional District 2", vintage_year=2020,
            geoid="0102", state_fips="01", state=self.state, district_number="02",
            geometry=EAST_HALF,
        )

        self.enacted = RedistrictingPlan.objects.create(
            state_fips="01", chamber="congress", cycle_year=2020,
            plan_name="AL Enacted", num_districts=7,
            effective_from=date(2022, 1, 3), effective_to=date(2023, 10, 4),
        )
        self.milligan = RedistrictingPlan.objects.create(
            state_fips="01", chamber="congress", cycle_year=2020,
            plan_name="Milligan Interim", num_districts=7,
            effective_from=date(2023, 10, 5),
        )
        # A plan for another state must never leak into a filtered lookup.
        self.texas = RedistrictingPlan.objects.create(
            state_fips="48", chamber="congress", cycle_year=2020,
            plan_name="TX Enacted", num_districts=38,
            effective_from=date(2022, 1, 3),
        )

        self.addr = Address.objects.create(
            primary_number="100", street_name="Main", state_abbreviation="AL",
            geocoded=True, geom=Point(-87.0, 33.5, srid=4326),
        )

    def _run(self, *args):
        out = StringIO()
        call_command("assign_boundaries", *args, stdout=out)
        self.addr.refresh_from_db()
        return out.getvalue()


class TestLegacyModeSpatialJoin(_AssignBoundariesBase):

    def test_assigns_census_boundaries(self):
        out = self._run("--year", "2020", "--state", "AL")

        assert "1/1 assigned, 0 failed" in out
        assert self.addr.state_geoid == "01"
        assert self.addr.county_geoid == "01073"
        assert self.addr.cd_geoid == "0107"
        assert self.addr.census_units_assigned_at is not None

    def test_address_outside_every_state_counts_as_failed(self):
        self.addr.geom = Point(-100.0, 40.0, srid=4326)
        self.addr.save()

        out = self._run("--year", "2020", "--state", "AL")

        assert "0/1 assigned, 1 failed" in out
        assert self.addr.census_units_assigned_at is None


class TestPlanAwareModeStateFilter(_AssignBoundariesBase):

    def setUp(self):
        super().setUp()
        from siege_utilities.geo.django.models import PlanDistrict

        # Under the Milligan plan the test address falls in CD-02, not the
        # Census-drawn CD-07.
        PlanDistrict.objects.create(
            feature_id="0102-milligan", name="District 2", vintage_year=2020,
            geoid="0102", state_fips="01", plan=self.milligan,
            district_number="2", geometry=WEST_HALF,
        )

    def test_state_abbreviation_uses_active_plan(self):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        out = self._run("--date", "2024-03-01", "--state", "AL")

        assert "Active plan: Milligan Interim" in out
        assert "1/1 assigned, 0 failed" in out
        assert self.addr.cd_geoid == "0102"
        period = AddressBoundaryPeriod.objects.get(address=self.addr)
        assert period.redistricting_plan == self.milligan
        assert period.assignment_method == "PLAN_SPATIAL_JOIN"
        assert period.cd_geoid == "0102"

    def test_falls_back_to_census_district_when_plan_has_no_match(self):
        from socialwarehouse.geo.models import AddressBoundaryPeriod

        # The enacted plan is active on this date but has no districts loaded.
        out = self._run("--date", "2023-08-15", "--state", "AL")

        assert "Active plan: AL Enacted" in out
        assert self.addr.cd_geoid == "0107"
        period = AddressBoundaryPeriod.objects.get(address=self.addr)
        assert period.redistricting_plan == self.enacted
        assert period.assignment_method == "SPATIAL_JOIN"


class TestFetchActivePlans(_AssignBoundariesBase):

    def _fetch(self, context_date, state_filter):
        from socialwarehouse.geo.management.commands.assign_boundaries import Command

        return Command()._fetch_active_plans(context_date, state_filter)

    def test_abbreviation(self):
        assert self._fetch(date(2023, 8, 15), "AL") == {("01", "congress"): self.enacted}

    def test_abbreviation_is_case_insensitive(self):
        assert self._fetch(date(2024, 3, 1), "al") == {("01", "congress"): self.milligan}

    def test_full_name_still_resolves(self):
        assert self._fetch(date(2024, 3, 1), "Alabama") == {("01", "congress"): self.milligan}

    def test_fips_code_still_resolves(self):
        assert self._fetch(date(2024, 3, 1), "01") == {("01", "congress"): self.milligan}

    def test_unknown_state_returns_no_plans(self):
        assert self._fetch(date(2024, 3, 1), "ZZ") == {}

    def test_no_filter_returns_every_state(self):
        plans = self._fetch(date(2024, 3, 1), None)
        assert plans == {("01", "congress"): self.milligan, ("48", "congress"): self.texas}
