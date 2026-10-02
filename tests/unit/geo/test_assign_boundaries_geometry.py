"""Regression tests for assign_boundaries / #376.

Three coupled defects on origin/develop @ 363a7fd (siege_utilities 3.23.0):
  (i)   boundary queries used ``geom__contains`` but siege_utilities boundary
        models store the polygon in ``geometry`` (TemporalBoundary). Every
        query raised FieldError, caught per-address, so every address was
        counted failed.
  (ii)  ``_fetch_active_plans`` resolved State by ``name``/``geoid`` only, so
        ``--state AL`` never matched and plan-aware mode silently fell back to
        Census districts.
  (iii) unmatched ``*_geoid`` levels were saved as ``None`` into NOT NULL
        CharField(default="") columns, so once (i) was fixed the save raised
        IntegrityError.

These tests exercise the real PostGIS spatial path (ci.yml runs them against
postgis/postgis:17-3.5). Mutation bite: revert the fix and at least one of
these goes red (see the file-level docstring in the PR for exact steps).

Why these assertions bite each defect:
  * test_legacy_assign_* asserts 1/1 assigned and the geoids persisted. Revert
    (i) -> FieldError -> 0/1 assigned. Revert (iii) -> IntegrityError on save
    -> 0/1 assigned. Either revert turns it red.
  * test_plan_aware_prefers_plan_district asserts the PlanDistrict geoid wins
    over the Census CD. Revert (i) -> FieldError -> not assigned. Revert (ii)
    -> no active plan found -> Census CD used instead -> wrong geoid.
  * test_fetch_active_plans_* asserts abbreviation/name/FIPS resolution. Revert
    (ii) -> abbreviation returns nothing -> red.
"""

from datetime import date

import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management import call_command
from django.test import TestCase

try:
    from io import StringIO
except ImportError:  # pragma: no cover - StringIO is always present on py3
    StringIO = None


# Central-Alabama-ish anchor. The NAD83<->WGS84 datum shift the command applies
# (query_point.transform(4269)) is sub-meter, far inside the degree-scale squares
# below, so containment holds regardless of transform direction.
AL_LON, AL_LAT = -86.8, 32.8
# A point well outside the Alabama squares (Pacific Northwest), used for the
# out-of-state case.
FAR_LON, FAR_LAT = -120.0, 45.0

VINTAGE = 2020
AL_FIPS = "01"


def _square(center_lon, center_lat, half):
    """A WGS84 MultiPolygon square centered on (lon, lat) with the given half-width."""
    poly = Polygon.from_bbox(
        (center_lon - half, center_lat - half, center_lon + half, center_lat + half)
    )
    poly.srid = 4326
    return MultiPolygon(poly, srid=4326)


def _big_al_square():
    # 6-degree half-width square around the anchor; contains AL_LON/AL_LAT and
    # dwarfs any datum shift. Does NOT contain FAR_LON/FAR_LAT.
    return _square(AL_LON, AL_LAT, 6.0)


def _al_point():
    return Point(AL_LON, AL_LAT, srid=4326)


def _far_point():
    return Point(FAR_LON, FAR_LAT, srid=4326)


def _make_state(**overrides):
    from siege_utilities.geo.django.models import State

    kwargs = dict(
        feature_id="AL",
        name="Alabama",
        abbreviation="AL",
        geoid=AL_FIPS,
        state_fips=AL_FIPS,
        vintage_year=VINTAGE,
        geometry=_big_al_square(),
    )
    kwargs.update(overrides)
    return State.objects.create(**kwargs)


def _make_county(**overrides):
    from siege_utilities.geo.django.models import County

    kwargs = dict(
        feature_id="01001",
        name="Test County",
        county_name="Test County",
        county_fips="001",
        geoid="01001",
        state_fips=AL_FIPS,
        vintage_year=VINTAGE,
        geometry=_big_al_square(),
    )
    kwargs.update(overrides)
    return County.objects.create(**kwargs)


def _make_census_cd(geoid="0199", geometry=None, **overrides):
    from siege_utilities.geo.django.models import CongressionalDistrict

    kwargs = dict(
        feature_id="cd-" + geoid,
        name="Census CD " + geoid,
        district_number=geoid[-2:],
        geoid=geoid,
        state_fips=AL_FIPS,
        vintage_year=VINTAGE,
        geometry=geometry if geometry is not None else _big_al_square(),
    )
    kwargs.update(overrides)
    return CongressionalDistrict.objects.create(**kwargs)


def _make_plan(**overrides):
    from siege_utilities.geo.django.models import RedistrictingPlan

    kwargs = dict(
        state_fips=AL_FIPS,
        chamber="congress",
        cycle_year=2022,
        plan_name="AL 2023 court-ordered congressional plan",
        num_districts=7,
        effective_from=date(2023, 1, 1),
        effective_to=None,
    )
    kwargs.update(overrides)
    return RedistrictingPlan.objects.create(**kwargs)


def _make_plan_district(plan, geoid="0107", geometry=None, **overrides):
    from siege_utilities.geo.django.models import PlanDistrict

    kwargs = dict(
        plan=plan,
        district_number="07",
        feature_id="pd-" + geoid,
        name="Plan district " + geoid,
        geoid=geoid,
        state_fips=AL_FIPS,
        vintage_year=VINTAGE,
        geometry=geometry if geometry is not None else _big_al_square(),
    )
    kwargs.update(overrides)
    return PlanDistrict.objects.create(**kwargs)


def _make_address(point=None, state="AL"):
    from socialwarehouse.geo.models import Address

    return Address.objects.create(
        geocoded=True,
        geom=point if point is not None else _al_point(),
        state_abbreviation=state,
    )


@pytest.mark.django_db
class TestAssignBoundariesGeometry(TestCase):
    def test_legacy_assign_sets_state_county_cd(self):
        """Legacy --year/--state assigns state/county/CD for an in-state address.

        Bites defect (i): revert geometry->geom and the State query raises
        FieldError, so assigned=0. Bites defect (iii): the address matches no
        Tract/BlockGroup/VTD/SLDL/SLDU, so without the "" coalesce the save
        writes None into NOT NULL columns and raises IntegrityError, again
        assigned=0.
        """
        _make_state()
        _make_county()
        _make_census_cd(geoid="0101")
        addr = _make_address()

        out = StringIO()
        call_command("assign_boundaries", year=VINTAGE, state="AL", stdout=out)

        assert "1/1 assigned, 0 failed" in out.getvalue()

        addr.refresh_from_db()
        assert addr.census_units_assigned_at is not None
        assert addr.state_geoid == AL_FIPS
        assert addr.county_geoid == "01001"
        assert addr.cd_geoid == "0101"
        # Unmatched levels must coalesce to "" (NOT NULL columns), never None.
        assert addr.tract_geoid == ""
        assert addr.block_group_geoid == ""
        assert addr.vtd_geoid == ""
        assert addr.sldl_geoid == ""
        assert addr.sldu_geoid == ""

    def test_out_of_state_address_counts_failed(self):
        """An address outside every state boundary is counted failed, not assigned."""
        _make_state()
        _make_county()
        _make_census_cd(geoid="0101")
        addr = _make_address(point=_far_point(), state="AL")

        out = StringIO()
        call_command("assign_boundaries", year=VINTAGE, state="AL", stdout=out)

        assert "0/1 assigned, 1 failed" in out.getvalue()
        addr.refresh_from_db()
        assert addr.census_units_assigned_at is None
        assert addr.state_geoid == ""

    def test_plan_aware_prefers_plan_district(self):
        """Plan-aware mode picks the PlanDistrict over the Census CD.

        Bites defect (ii): revert the abbreviation fix and _fetch_active_plans
        returns nothing for "AL", so the command falls back to the Census CD
        and cd_geoid becomes "0199" instead of the plan's "0107".
        """
        _make_state()
        _make_county()
        _make_census_cd(geoid="0199")  # Census CD also contains the point
        plan = _make_plan()
        _make_plan_district(plan, geoid="0107")  # Plan district contains the point

        addr = _make_address()

        out = StringIO()
        call_command("assign_boundaries", date="2023-08-15", state="AL", stdout=out)

        assert "1/1 assigned, 0 failed" in out.getvalue()
        addr.refresh_from_db()
        assert addr.cd_geoid == "0107"

    def test_plan_aware_falls_back_to_census_cd_when_plan_has_no_district(self):
        """If the active plan has no district covering the point, use the Census CD."""
        _make_state()
        _make_county()
        _make_census_cd(geoid="0199")
        plan = _make_plan()
        # Plan district is far away (disjoint from the address point).
        _make_plan_district(
            plan, geoid="0107", geometry=_square(FAR_LON, FAR_LAT, 1.0)
        )

        addr = _make_address()

        out = StringIO()
        call_command("assign_boundaries", date="2023-08-15", state="AL", stdout=out)

        assert "1/1 assigned, 0 failed" in out.getvalue()
        addr.refresh_from_db()
        assert addr.cd_geoid == "0199"


@pytest.mark.django_db
class TestFetchActivePlansResolution(TestCase):
    """_fetch_active_plans must resolve abbreviation (case-insensitive), full
    name, and FIPS; return nothing for an unknown state; and preserve the
    unfiltered all-states path. Bites defect (ii)."""

    def _command(self):
        from socialwarehouse.geo.management.commands.assign_boundaries import Command

        return Command()

    def setUp(self):
        _make_state()
        self.plan = _make_plan()
        self.when = date(2023, 8, 15)
        self.key = (AL_FIPS, "congress")

    def test_resolves_abbreviation(self):
        plans = self._command()._fetch_active_plans(self.when, "AL")
        assert self.key in plans

    def test_resolves_abbreviation_case_insensitive(self):
        plans = self._command()._fetch_active_plans(self.when, "al")
        assert self.key in plans

    def test_resolves_full_name(self):
        plans = self._command()._fetch_active_plans(self.when, "Alabama")
        assert self.key in plans

    def test_resolves_fips(self):
        plans = self._command()._fetch_active_plans(self.when, "01")
        assert self.key in plans

    def test_unknown_state_returns_nothing(self):
        plans = self._command()._fetch_active_plans(self.when, "ZZ")
        assert plans == {}

    def test_all_states_path_preserved(self):
        plans = self._command()._fetch_active_plans(self.when, None)
        assert self.key in plans
