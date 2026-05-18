"""Regression tests for A6 (SW#117): boundary-type lookup helper.

The fix extracts the 3x-duplicated BOUNDARY_MODELS.get-or-400 pattern
from boundary_list, boundary_detail, and proximity into a single
`_resolve_boundary_model` helper. boundary_detail previously returned a
400 WITHOUT a `valid_types` list (inconsistent with the other two);
the helper standardizes the response shape.

Tests cover:
  - helper returns (model, None) on a known type
  - helper returns (None, Response) on a miss, with valid_types in body
  - each of the 3 call sites invokes the helper AND returns the error
    response on miss (not just silently swallowing it)

NOTE on test design: source-grep regressions read views.py as text rather
than via inspect.getsource() — DRF's @api_view returns a closure wrapper
whose source is `def view(request, *args, **kwargs): self.dispatch(...)`,
NOT the decorated function's source. See claude-configs-public#123
(writing-tests inspection-vs-behavior) for the rule-gap that this
session surfaced. An end-to-end APIClient test against boundary_detail's
400 shape is intentionally NOT in this file because boundary_detail's
A1 fix (PR #122) is on a sibling unmerged branch — until #122 merges
into this PR's base, calling boundary_detail via APIClient hits the
class-based-view-shape decorator bug and raises TypeError before the
view body executes. The helper-level test below proves the response
shape; the source-grep tests prove the call site uses it correctly.
"""

from pathlib import Path

from django.test import TestCase

from socialwarehouse.api.geo import views

_VIEWS_SOURCE = Path(views.__file__).read_text(encoding="utf-8")


def _function_block(name):
    """Return decorator stack + def header + body for a top-level function.

    Walks source line-by-line, finds `def <name>(`, walks backwards
    through immediately-preceding `@`-decorator lines, walks forward until
    the next top-level `def `/`class ` or end of file.
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


class TestResolveBoundaryModelHelper(TestCase):

    def test_helper_returns_model_on_known_type(self):
        model, err = views._resolve_boundary_model("state")
        assert err is None
        assert model is views.BOUNDARY_MODELS["state"]

    def test_helper_returns_400_with_valid_types_on_miss(self):
        model, err = views._resolve_boundary_model("definitely-not-a-real-type")
        assert model is None
        assert err is not None
        assert err.status_code == 400
        assert "error" in err.data
        assert "definitely-not-a-real-type" in err.data["error"]
        # Helper standardizes inclusion of valid_types — this is the
        # response-shape guarantee that boundary_detail's 400 inherits.
        assert "valid_types" in err.data
        assert set(err.data["valid_types"]) == set(views.BOUNDARY_MODELS.keys())


class TestCallSitesUseHelper(TestCase):
    """Each of the 3 call sites must call the helper AND return the error
    response on miss. The helper-call check goes red if anyone re-inlines
    BOUNDARY_MODELS.get + Response(400). The return-err check goes red if
    anyone calls the helper but ignores its error path (silently swallowing
    a 400 case would be its own bug)."""

    def _assert_uses_helper_and_returns_err(self, fn_name):
        block = _function_block(fn_name)
        assert block, f"could not find {fn_name} in views.py"
        assert "_resolve_boundary_model(" in block, (
            f"{fn_name} must call _resolve_boundary_model() (A6/#117)"
        )
        assert "BOUNDARY_MODELS.get(" not in block, (
            f"{fn_name} must NOT re-inline BOUNDARY_MODELS.get + Response(400) — "
            f"use the helper (A6/#117)"
        )
        # The helper returns (model, err); callers must return err on miss.
        # Accept either `return err` (current shape) or `return err_response`.
        assert "return err" in block or "return error" in block, (
            f"{fn_name} must return the helper's error response on miss; "
            f"calling the helper but discarding the err half is its own bug"
        )

    def test_boundary_list(self):
        self._assert_uses_helper_and_returns_err("boundary_list")

    def test_boundary_detail(self):
        self._assert_uses_helper_and_returns_err("boundary_detail")

    def test_proximity(self):
        self._assert_uses_helper_and_returns_err("proximity")


class TestLoopSitesUntouched(TestCase):
    """The 2 loop sites (geocode, _get_demographics_for_boundaries) have
    silent-skip semantics and intentionally do NOT use the helper. Confirms
    A6's scope boundary holds — going red if anyone over-applies the
    helper to a loop site."""

    def test_geocode_keeps_inline_lookup(self):
        block = _function_block("geocode")
        # geocode iterates requested_types and continues on miss; no error
        # response shape. The inline lookup is correct here.
        assert "BOUNDARY_MODELS.get(" in block, (
            "geocode's loop-with-silent-skip is out of A6 scope; "
            "if the inline lookup is gone, scope decision changed — "
            "update docs/entities/api_geo_views_decorators.md to match"
        )
