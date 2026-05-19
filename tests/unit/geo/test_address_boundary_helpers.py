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


class TestBoundaryOn(TestCase):
    """boundary_on: single-type sugar over boundaries_on."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)
        self.addr = Address.objects.create(state_abbreviation="GA")

        self.abp = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=vintage,
            state_geoid="13",
            county_geoid="13089",
            context_date=date(2023, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )

    def test_returns_row_when_type_present(self):
        result = self.addr.boundary_on("county", date(2023, 6, 1))
        assert result == self.abp

    def test_returns_none_when_type_absent(self):
        # No cd_geoid on the row, so cd should resolve to None.
        result = self.addr.boundary_on("cd", date(2023, 6, 1))
        assert result is None

    def test_unknown_boundary_type_raises(self):
        import pytest

        with pytest.raises(ValueError) as exc:
            self.addr.boundary_on("precinct", date(2023, 6, 1))
        assert "precinct" in str(exc.value)


class TestBoundaryAt(TestCase):
    """boundary_at: positional access into reverse-chron history (0-indexed)."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)
        self.addr = Address.objects.create(state_abbreviation="AL")

        # Three CD-bearing periods, oldest first; will sort newest-first.
        self.abp_old = AddressBoundaryPeriod.objects.create(
            address=self.addr, vintage=vintage,
            cd_geoid="0107", context_date=date(2020, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )
        self.abp_mid = AddressBoundaryPeriod.objects.create(
            address=self.addr, vintage=vintage,
            redistricting_plan_id=1,
            cd_geoid="0102", context_date=date(2022, 6, 1),
            assignment_method="PLAN_SPATIAL_JOIN",
        )
        self.abp_new = AddressBoundaryPeriod.objects.create(
            address=self.addr, vintage=vintage,
            redistricting_plan_id=2,
            cd_geoid="0102", context_date=date(2024, 6, 1),
            assignment_method="PLAN_SPATIAL_JOIN",
        )

    def test_position_zero_is_most_recent(self):
        result = self.addr.boundary_at("cd", 0)
        assert result == self.abp_new

    def test_position_n_walks_back_in_time(self):
        assert self.addr.boundary_at("cd", 1) == self.abp_mid
        assert self.addr.boundary_at("cd", 2) == self.abp_old

    def test_out_of_range_returns_none(self):
        assert self.addr.boundary_at("cd", 50) is None

    def test_negative_position_raises(self):
        import pytest

        with pytest.raises(ValueError):
            self.addr.boundary_at("cd", -1)

    def test_unknown_boundary_type_raises(self):
        import pytest

        with pytest.raises(ValueError) as exc:
            self.addr.boundary_at("precinct", 0)
        assert "precinct" in str(exc.value)

    def test_slice_via_queryset_for_ranges(self):
        # Documenting the canonical range pattern: use queryset slicing
        # directly rather than a separate boundary_range helper.
        history = self.addr.boundary_history(boundary_type="cd")
        rows = list(history[1:3])
        assert rows == [self.abp_mid, self.abp_old]


class TestGeoidOn(TestCase):
    """geoid_on: one-step GEOID string lookup, None-safe."""

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)
        self.addr = Address.objects.create(state_abbreviation="MI")

        AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=vintage,
            state_geoid="26",
            county_geoid="26163",
            context_date=date(2023, 1, 1),
            assignment_method="SPATIAL_JOIN",
        )

    def test_returns_string_when_present(self):
        assert self.addr.geoid_on("county", date(2023, 6, 1)) == "26163"

    def test_returns_none_when_type_absent(self):
        assert self.addr.geoid_on("cd", date(2023, 6, 1)) is None

    def test_returns_none_when_no_row(self):
        from socialwarehouse.geo.models import Address

        other = Address.objects.create(state_abbreviation="OH")
        assert other.geoid_on("county", date(2023, 6, 1)) is None

    def test_unknown_boundary_type_raises(self):
        import pytest

        with pytest.raises(ValueError):
            self.addr.geoid_on("precinct", date(2023, 6, 1))


class TestCurrentGeoid(TestCase):
    """current_geoid: geoid_on(today) sugar."""

    def test_delegates_to_today(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )
        from django.utils import timezone

        CensusVintageConfig.seed_defaults()
        vintage = CensusVintageConfig.objects.get(decade=2020)
        addr = Address.objects.create(state_abbreviation="WA")

        AddressBoundaryPeriod.objects.create(
            address=addr,
            vintage=vintage,
            state_geoid="53",
            county_geoid="53033",
            context_date=timezone.localdate(),
            assignment_method="SPATIAL_JOIN",
        )

        assert addr.current_geoid("state") == "53"
        assert addr.current_geoid("county") == "53033"
        assert addr.current_geoid("cd") is None


class TestBoundaryTimeline(TestCase):
    """boundary_timeline: chronological list of BoundaryTimelineEntry tuples.

    Effective ranges are derived from ABP rows' ``context_date`` field
    (entry N's effective_to = entry N+1's effective_from - 1 day; the
    most recent entry's effective_to is None). Plan-side effective
    dates are NOT consulted today (SU#527 — RedistrictingPlan declares
    `effective_from` / `effective_to` but the SU migrations don't
    create those columns). When SU#527 lands and SW bumps its pin, a
    follow-up should restore plan-side date preference where available.
    """

    def setUp(self):
        from socialwarehouse.geo.models import (
            Address, AddressBoundaryPeriod, CensusVintageConfig,
        )

        CensusVintageConfig.seed_defaults()
        self.vintage_2010 = CensusVintageConfig.objects.get(decade=2010)
        self.vintage_2020 = CensusVintageConfig.objects.get(decade=2020)

        self.addr = Address.objects.create(state_abbreviation="AL")

        # Two NULL-plan rows on different vintages.
        self.abp_2010 = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2010,
            cd_geoid="0107",
            context_date=date(2015, 6, 1),
            assignment_method="SPATIAL_JOIN",
        )
        self.abp_2020 = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            cd_geoid="0107",
            context_date=date(2021, 6, 1),
            assignment_method="SPATIAL_JOIN",
        )
        # Orphan-FK row (plan_id points to a non-existent row).
        self.abp_orphan = AddressBoundaryPeriod.objects.create(
            address=self.addr,
            vintage=self.vintage_2020,
            redistricting_plan_id=999_999,
            cd_geoid="0102",
            context_date=date(2024, 6, 1),
            assignment_method="PLAN_SPATIAL_JOIN",
        )

    def test_entries_are_oldest_first(self):
        timeline = self.addr.boundary_timeline("cd")
        assert len(timeline) == 3
        assert timeline[0].abp == self.abp_2010
        assert timeline[1].abp == self.abp_2020
        assert timeline[2].abp == self.abp_orphan

    def test_effective_range_threads_through_context_date(self):
        timeline = self.addr.boundary_timeline("cd")
        # Entry 0 (oldest): from its own context_date, to the day before entry 1.
        assert timeline[0].effective_from == date(2015, 6, 1)
        assert timeline[0].effective_to == date(2021, 5, 31)
        # Entry 1: from its context_date, to the day before entry 2.
        assert timeline[1].effective_from == date(2021, 6, 1)
        assert timeline[1].effective_to == date(2024, 5, 31)
        # Entry 2 (newest): from its context_date; effective_to is None.
        assert timeline[2].effective_from == date(2024, 6, 1)
        assert timeline[2].effective_to is None

    def test_plan_name_is_none_for_null_plan_rows(self):
        timeline = self.addr.boundary_timeline("cd")
        assert timeline[0].plan_name is None
        assert timeline[1].plan_name is None

    def test_orphan_fk_resolves_plan_name_to_none(self):
        # redistricting_plan_id=999_999 doesn't exist; _safe_plan_name
        # returns None without raising.
        timeline = self.addr.boundary_timeline("cd")
        assert timeline[2].plan_name is None

    def test_entry_carries_geoid_and_abp(self):
        timeline = self.addr.boundary_timeline("cd")
        assert timeline[0].geoid == "0107"
        assert timeline[2].geoid == "0102"
        assert timeline[0].abp == self.abp_2010

    def test_entry_namedtuple_unpacks(self):
        timeline = self.addr.boundary_timeline("cd")
        geoid, eff_from, eff_to, plan_name, abp = timeline[0]
        assert geoid == "0107"
        assert eff_from == date(2015, 6, 1)
        assert eff_to == date(2021, 5, 31)
        assert plan_name is None
        assert abp == self.abp_2010

    def test_unknown_boundary_type_raises(self):
        import pytest

        with pytest.raises(ValueError):
            self.addr.boundary_timeline("precinct")

    def test_empty_when_no_rows_of_type(self):
        # No sldl_geoid populated on any row.
        assert self.addr.boundary_timeline("sldl") == []

    def test_isolation_between_addresses(self):
        from socialwarehouse.geo.models import Address

        other = Address.objects.create(state_abbreviation="GA")
        assert other.boundary_timeline("cd") == []


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
