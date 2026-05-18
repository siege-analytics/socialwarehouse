"""Regression tests for socialwarehouse.api.geo.views fixes.

A1 (gh #112): boundary_detail used `@method_decorator(cache_page, name="dispatch")`,
which is class-based-view shape and silently no-ops on function-based DRF views.

A3 (gh #114): `_forward_geocode` / `_reverse_geocode` swallowed all exceptions
with `except Exception: pass`, hiding geocoder/network failures from operators.

These tests are designed to GO RED on revert.
"""

import inspect
import logging
from unittest import mock

from django.test import TestCase

from socialwarehouse.api.geo import views


class TestBoundaryDetailCacheDecorator(TestCase):
    """A1: boundary_detail must use cache_page directly (not method_decorator)."""

    def test_boundary_detail_source_uses_cache_page_directly(self):
        """The source must apply @cache_page above the function, not via method_decorator(name='dispatch').

        Goes red if anyone re-introduces the method_decorator(..., name="dispatch")
        shape on this function-based view.
        """
        src = inspect.getsource(views.boundary_detail)
        assert "@cache_page(" in src, "boundary_detail must have @cache_page applied directly"
        assert 'name="dispatch"' not in src and "name='dispatch'" not in src, (
            "method_decorator(..., name='dispatch') is class-based-view shape; "
            "function-based DRF views have no dispatch attribute"
        )

    def test_boundary_detail_module_does_not_import_method_decorator(self):
        """method_decorator import was removed as part of the A1 fix."""
        src = inspect.getsource(views)
        assert "from django.utils.decorators import method_decorator" not in src


class TestGeocodeHelpersLogFailures(TestCase):
    """A3: _forward_geocode / _reverse_geocode must log exceptions, not swallow."""

    def test_forward_geocode_logs_on_exception(self):
        with mock.patch(
            "siege_utilities.geo.geocoding.get_coordinates",
            side_effect=RuntimeError("geocoder down"),
        ):
            with self.assertLogs("socialwarehouse.api.geo", level="WARNING") as cm:
                result = views._forward_geocode("123 Main St")
        assert result is None
        assert any("_forward_geocode failed" in msg for msg in cm.output)
        assert any("RuntimeError" in msg for msg in cm.output)

    def test_reverse_geocode_logs_on_exception(self):
        with mock.patch(
            "geopy.geocoders.Nominatim",
            side_effect=RuntimeError("nominatim unreachable"),
        ):
            with self.assertLogs("socialwarehouse.api.geo", level="WARNING") as cm:
                result = views._reverse_geocode(40.0, -74.0)
        assert result is None
        assert any("_reverse_geocode failed" in msg for msg in cm.output)
        assert any("RuntimeError" in msg for msg in cm.output)

    def test_geocode_helper_sources_have_no_bare_except_pass(self):
        """Goes red if anyone restores `except Exception: pass` in either helper."""
        for fn in (views._forward_geocode, views._reverse_geocode):
            src = inspect.getsource(fn)
            normalized = "\n".join(line.rstrip() for line in src.splitlines())
            assert "except Exception:\n        pass" not in normalized, (
                f"{fn.__name__} must not silently swallow exceptions (writing-code:7)"
            )
