"""
Regression tests for warehouse dimension loader / schema alignment surfaced
by the E1 hostile review.

Each test corresponds to a child issue of #49 and exists specifically to
fail on revert of the named fix. Per writing-tests:1.

Origin: E1 hostile review pass 2026-05-17.
"""

import pytest


class TestDimTimeSchemaAlignment:
    """Regression tests for #105 (W1): DimTime schema must include the
    fields the loader writes.
    """

    def test_dimtime_has_loader_required_fields(self):
        """W1 regression: the 6 fields the loader writes must exist on
        the model. Goes red if any field is removed from DimTime.
        """
        from socialwarehouse.warehouse.models import DimTime

        field_names = {f.name for f in DimTime._meta.get_fields()}

        # Fields the loader (dimension_loader.py:118-132) writes via
        # update_or_create(defaults=...) and must exist on the model:
        required = {
            "day_of_month",
            "day_of_week",
            "week_of_year",
            "is_presidential_election",
            "is_midterm_election",
            "federal_fiscal_year",
        }
        missing = required - field_names
        assert not missing, (
            f"DimTime is missing fields the loader writes: {missing} "
            "(W1 / #105 regression)."
        )

    def test_dimtime_does_not_have_renamed_old_field(self):
        """W1: the rename `fiscal_year -> federal_fiscal_year` must be
        intact. If both exist OR only `fiscal_year` exists, the migration
        didn't apply or someone reverted.
        """
        from socialwarehouse.warehouse.models import DimTime

        field_names = {f.name for f in DimTime._meta.get_fields()}
        assert "federal_fiscal_year" in field_names, (
            "DimTime is missing federal_fiscal_year (W1 / #105 regression)."
        )
        assert "fiscal_year" not in field_names, (
            "DimTime still has old fiscal_year alongside federal_fiscal_year. "
            "Rename incomplete (W1 / #105 regression)."
        )


class TestDimRedistrictingCycleSchemaAlignment:
    """Regression tests for #106 (W2): DimRedistrictingCycle schema must
    include the fields the loader writes (and not the wrong-named ones).
    """

    def test_dimredistrictingcycle_has_loader_required_fields(self):
        """W2 regression: census_year + effective_start + effective_end +
        first_election_year must exist; old decennial_census_year must
        NOT (rename), and first_election_year must be writable (loader
        supplies it).
        """
        from socialwarehouse.warehouse.models import DimRedistrictingCycle

        field_names = {f.name for f in DimRedistrictingCycle._meta.get_fields()}

        required = {
            "census_year",
            "first_election_year",
            "effective_start",
            "effective_end",
        }
        missing = required - field_names
        assert not missing, (
            f"DimRedistrictingCycle is missing loader-required fields: {missing} "
            "(W2 / #106 regression)."
        )
        assert "decennial_census_year" not in field_names, (
            "DimRedistrictingCycle still has old decennial_census_year alongside "
            "census_year. Rename incomplete (W2 / #106 regression)."
        )

    def test_dimredistrictingcycle_loader_supplies_first_election_year(self):
        """W2: the loader was missing the required first_election_year
        write. Verify the loader source string contains the assignment.
        Source-string check rather than full exercise because the loader
        requires a real DB with RedistrictingPlan rows; source check is
        the structural floor.
        """
        import inspect
        from socialwarehouse.warehouse.services import dimension_loader

        src = inspect.getsource(dimension_loader.DimensionLoaderService.load_redistricting_cycles)
        assert "first_election_year" in src, (
            "load_redistricting_cycles no longer supplies first_election_year "
            "(W2 / #106 regression)."
        )


class TestFactRedistrictingPlanUniqueness:
    """Regression tests for #107 (W3): FactRedistrictingPlan must have
    unique_together to prevent duplicate plan-fact rows.
    """

    def test_factredistrictingplan_has_unique_together(self):
        """W3 regression: unique_together must declare the canonical key.
        Verifies Meta declares the constraint over the right field set.
        """
        from socialwarehouse.warehouse.models import FactRedistrictingPlan

        ut = FactRedistrictingPlan._meta.unique_together
        # Django stores unique_together as a tuple of tuples. Check the
        # canonical key set is present.
        canonical = frozenset(["geography", "cycle", "chamber", "plan_type", "district_number"])
        found = any(frozenset(group) == canonical for group in ut)
        assert found, (
            f"FactRedistrictingPlan unique_together missing canonical key set "
            f"{sorted(canonical)} (W3 / #107 regression). Current: {ut}"
        )
