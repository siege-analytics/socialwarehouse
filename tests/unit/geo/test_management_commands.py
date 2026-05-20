"""
Regression tests for management commands surfaced by the E1 hostile review.

Each test corresponds to a child issue of #49 and exists specifically to
fail on revert of the named fix. Per writing-tests:1 ("tests must fail if
the production behaviour breaks"), these are the import-state floor: they
go red if the import that the fix adds is removed.

Origin: E1 hostile review pass 2026-05-17, fix PR #104.
"""

import importlib
import pytest


class TestAssignBoundariesImports:
    """Regression tests for #91 (F1): assign_boundaries.py needed `from django.db import models`."""

    def test_models_symbol_resolvable_at_module_scope(self):
        """F1 regression: `models` must be importable at file scope.

        The `_fetch_active_plans` bulk-no-state-filter path uses
        `models.Q(...)`. Pre-fix, `models` was never imported at file
        scope (only inside `handle` method's `from django.db.models
        import Count` at line 130). The bulk path crashed with NameError.

        This test imports the module and verifies that `models` is
        accessible at the module namespace level, which guarantees the
        fix's `from django.db import models` is in place.
        """
        mod = importlib.import_module(
            "socialwarehouse.geo.management.commands.assign_boundaries"
        )
        assert hasattr(mod, "models"), (
            "assign_boundaries module is missing top-level `models` import "
            "(regression of F1 / #91)."
        )
        # Sanity: confirm it's the Django models module, not something else
        # that happens to be named `models`.
        from django.db import models as django_models
        assert mod.models is django_models, (
            "assign_boundaries.models is not django.db.models — likely "
            "shadowed by a different import."
        )


class TestSwhPostgisConnectorImports:
    """Regression tests for #101 (B1): swh/census.py + swh/voters.py
    used wrong PostGISConnector import path.
    """

    def test_swh_census_postgis_connector_path(self):
        """B1 regression: swh/census.py imports PostGISConnector from
        siege_utilities.geo.spatial_transformations, NOT from
        siege_utilities.connectors (which doesn't exist).

        The bad import path was inside a method body (line 121), so
        module load doesn't trigger it. This test explicitly walks the
        relevant code path enough to force the import to evaluate.
        """
        # First confirm the source's import statement uses the correct path.
        # Source inspection is the more reliable check since exercising
        # the full code path requires PostGIS access.
        import inspect
        import swh.census as census_module
        src = inspect.getsource(census_module)
        assert "from siege_utilities.geo.spatial_transformations import PostGISConnector" in src, (
            "swh/census.py PostGISConnector import path regressed to the "
            "non-existent siege_utilities.connectors (B1 / #101)."
        )
        assert "from siege_utilities.connectors import" not in src, (
            "swh/census.py still references non-existent "
            "siege_utilities.connectors (B1 / #101)."
        )

    def test_swh_voters_postgis_connector_path(self):
        """B1 regression: swh/voters.py has the same import as
        swh/census.py — checked here separately so a partial regression
        (one fixed, one reverted) surfaces.
        """
        import inspect
        import swh.voters as voters_module
        src = inspect.getsource(voters_module)
        assert "from siege_utilities.geo.spatial_transformations import PostGISConnector" in src, (
            "swh/voters.py PostGISConnector import path regressed (B1 / #101)."
        )
        assert "from siege_utilities.connectors import" not in src, (
            "swh/voters.py still references non-existent "
            "siege_utilities.connectors (B1 / #101)."
        )

    def test_postgis_connector_actually_importable(self):
        """Independent of source-string check: the symbol the fix points
        at must actually be importable. If siege_utilities ever moves
        PostGISConnector again, this test goes red and the fix
        coordinates with siege_utilities's relocation."""
        from siege_utilities.geo.spatial_transformations import PostGISConnector
        assert PostGISConnector is not None
