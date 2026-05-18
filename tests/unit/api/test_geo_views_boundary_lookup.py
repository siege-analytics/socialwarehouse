"""Regression tests for A6 (SW#117): boundary-type lookup helper.

The fix extracts the 3x-duplicated BOUNDARY_MODELS.get-or-400 pattern
from boundary_list, boundary_detail, and proximity into a single
`_resolve_boundary_model` helper. boundary_detail previously returned a
400 WITHOUT a `valid_types` list (inconsistent with the other two);
the helper standardizes the response shape.

Tests:
  - helper returns (model, None) on a known type
  - helper returns (None, Response) on a miss, with valid_types in body
  - boundary_detail's 400 response now includes valid_types
"""

import inspect

from django.test import TestCase
from rest_framework.test import APIClient

from socialwarehouse.api.geo import views


class TestResolveBoundaryModelHelper(TestCase):

    def test_helper_returns_model_on_known_type(self):
        # Use any registered type. "state" is in BOUNDARY_MODELS.
        model, err = views._resolve_boundary_model("state")
        assert err is None
        assert model is views.BOUNDARY_MODELS["state"]

    def test_helper_returns_400_with_valid_types_on_miss(self):
        model, err = views._resolve_boundary_model("definitely-not-a-real-type")
        assert model is None
        assert err is not None
        # rest_framework Response — body accessible via .data
        assert err.status_code == 400
        assert "error" in err.data
        assert "definitely-not-a-real-type" in err.data["error"]
        # Helper standardizes inclusion of valid_types.
        assert "valid_types" in err.data
        assert set(err.data["valid_types"]) == set(views.BOUNDARY_MODELS.keys())


class TestBoundaryDetailErrorIncludesValidTypes(TestCase):
    """A6 also fixed an inconsistency: boundary_detail's 400 response
    used to omit valid_types; now it includes them via the helper."""

    def setUp(self):
        self.client = APIClient()

    def test_unknown_boundary_type_in_detail_returns_valid_types(self):
        response = self.client.get("/api/geo/boundaries/nonexistent/abc123/")
        assert response.status_code == 400
        body = response.json()
        assert "valid_types" in body, (
            "boundary_detail's 400 must include valid_types after A6/#117 "
            "(was inconsistent with boundary_list and proximity pre-fix)"
        )


class TestCallSitesUseHelper(TestCase):
    """Source-grep regression: the 3 error-responding sites must use the
    helper, not inline BOUNDARY_MODELS.get + Response(400). Goes red if
    anyone re-inlines the pattern in any of the 3 functions."""

    def test_boundary_list_uses_helper(self):
        src = inspect.getsource(views.boundary_list)
        assert "_resolve_boundary_model(" in src
        assert "BOUNDARY_MODELS.get(" not in src

    def test_boundary_detail_uses_helper(self):
        src = inspect.getsource(views.boundary_detail)
        assert "_resolve_boundary_model(" in src
        assert "BOUNDARY_MODELS.get(" not in src

    def test_proximity_uses_helper(self):
        src = inspect.getsource(views.proximity)
        assert "_resolve_boundary_model(" in src
        assert "BOUNDARY_MODELS.get(" not in src
