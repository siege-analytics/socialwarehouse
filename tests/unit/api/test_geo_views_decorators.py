"""Regression tests for socialwarehouse.api.geo.views fixes.

A1 (gh #112): boundary_detail used `@method_decorator(cache_page, name="dispatch")`,
which is class-based-view shape and silently no-ops on function-based DRF views.

A3 (gh #114): `_forward_geocode` / `_reverse_geocode` swallowed all exceptions
with `except Exception: pass`, hiding geocoder/network failures from operators.

These tests are designed to GO RED on revert.
"""

import logging
import re
from pathlib import Path
from unittest import mock

from django.test import TestCase

from socialwarehouse.api.geo import views

# Read the module file as text. `inspect.getsource(views.<decorated_fn>)`
# returns the DRF api_view closure wrapper, not the actual source — so for
# source-shape regressions we read the file directly. Per writing-tests
# inspection-vs-behavior note: source-grep tests must inspect text, not
# decorated function objects.
_VIEWS_FILE = Path(views.__file__)
_VIEWS_SOURCE = _VIEWS_FILE.read_text(encoding="utf-8")


def _function_block(name):
    """Return the decorator stack + def header + body for a top-level function.

    Walks the source line-by-line, finds `def <name>(`, walks backwards
    through immediately-preceding `@`-decorator lines, and walks forward
    until the next top-level `def `/`class ` or end of file. Sufficient
    for shape-of-decorators checks.
    """
    lines = _VIEWS_SOURCE.splitlines()
    def_idx = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {name}("):
            def_idx = i
            break
    if def_idx is None:
        return ""
    start = def_idx
    while start > 0 and lines[start - 1].startswith("@"):
        start -= 1
    end = def_idx + 1
    while end < len(lines) and not (
        lines[end].startswith("def ") or lines[end].startswith("class ")
    ):
        end += 1
    return "\n".join(lines[start:end])


class TestBoundaryDetailCacheDecorator(TestCase):
    """A1: boundary_detail must use cache_page directly (not method_decorator)."""

    def test_boundary_detail_source_uses_cache_page_directly(self):
        """The source must apply @cache_page above the function, not via method_decorator(name='dispatch').

        Goes red if anyone re-introduces the method_decorator(..., name="dispatch")
        shape on this function-based view.
        """
        block = _function_block("boundary_detail")
        assert "@cache_page(" in block, "boundary_detail must have @cache_page applied directly"
        assert 'name="dispatch"' not in block and "name='dispatch'" not in block, (
            "method_decorator(..., name='dispatch') is class-based-view shape; "
            "function-based DRF views have no dispatch attribute"
        )

    def test_boundary_detail_module_does_not_import_method_decorator(self):
        """method_decorator import was removed as part of the A1 fix."""
        assert "from django.utils.decorators import method_decorator" not in _VIEWS_SOURCE


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
        """Goes red if anyone restores `except Exception: pass` in either helper.

        Helpers are non-decorated module-level functions, so reading the file
        text is the same shape as inspect.getsource — but we use file text
        for uniformity with the boundary_detail tests above.
        """
        for fn_name in ("_forward_geocode", "_reverse_geocode"):
            block = _function_block(fn_name)
            normalized = "\n".join(line.rstrip() for line in block.splitlines())
            assert "except Exception:\n        pass" not in normalized, (
                f"{fn_name} must not silently swallow exceptions (writing-code:7)"
            )
