"""Unit tests for the DSTK replacement geo API."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


def _authenticate(client):
    """Authenticate an APIClient with a test user.

    A9 / SW#120: all api views require authentication. Tests exercising
    endpoint logic (validation, response shape) use force_authenticate
    so the auth gate doesn't mask the logic under test.
    Anonymous-access enforcement is covered in
    TestGeoAPIAuthenticationRequired.
    """
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="api_test_user")
    client.force_authenticate(user=user)
    return user


class TestGeoAPIEndpoints(TestCase):
    """Test that API endpoints respond correctly."""

    def setUp(self):
        self.client = APIClient()
        _authenticate(self.client)

    def test_geocode_requires_params(self):
        response = self.client.get("/api/geo/geocode/")
        assert response.status_code == 400
        assert "error" in response.json()

    def test_geocode_bad_coords(self):
        response = self.client.get("/api/geo/geocode/", {"lat": "abc", "lon": "def"})
        assert response.status_code == 400

    def test_reverse_geocode_requires_params(self):
        response = self.client.get("/api/geo/reverse_geocode/")
        assert response.status_code == 400

    def test_standardize_address_requires_param(self):
        response = self.client.get("/api/geo/standardize_address/")
        assert response.status_code == 400

    def test_standardize_address_parses(self):
        response = self.client.get(
            "/api/geo/standardize_address/",
            {"address": "123 Main St, Springfield, IL 62701"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["standardized"]["components"]["street"] == "123 Main St"
        assert data["standardized"]["components"]["city"] == "Springfield"
        assert data["standardized"]["components"]["state"] == "IL"
        assert data["standardized"]["components"]["zip"] == "62701"

    def test_boundary_list_unknown_type(self):
        response = self.client.get("/api/geo/boundaries/nonexistent/")
        assert response.status_code == 400
        assert "valid_types" in response.json()

    def test_proximity_requires_params(self):
        response = self.client.get("/api/geo/proximity/")
        assert response.status_code == 400

    def test_intersections_requires_params(self):
        response = self.client.get("/api/geo/intersections/")
        assert response.status_code == 400


class TestWarehouseAPIEndpoints(TestCase):
    """Test warehouse API endpoints respond."""

    def setUp(self):
        self.client = APIClient()
        _authenticate(self.client)

    def test_geographies_list(self):
        response = self.client.get("/api/warehouse/geographies/")
        assert response.status_code == 200

    def test_election_results_list(self):
        response = self.client.get("/api/warehouse/election-results/")
        assert response.status_code == 200

    def test_acs_estimates_list(self):
        response = self.client.get("/api/warehouse/acs-estimates/")
        assert response.status_code == 200


class TestGeoAPIAuthenticationRequired(TestCase):
    """A9 / SW#120: anonymous clients are denied. Regression guard
    against accidental permission_classes removal or DEFAULT_PERMISSION_CLASSES
    rollback.
    """

    def setUp(self):
        self.anon = APIClient()  # no auth

    def test_anonymous_geocode_denied(self):
        response = self.anon.get("/api/geo/geocode/", {"lat": "30.0", "lon": "-97.0"})
        assert response.status_code in (401, 403), (
            f"Expected 401/403 for anonymous access; got {response.status_code}"
        )

    def test_anonymous_boundary_list_denied(self):
        response = self.anon.get("/api/geo/boundaries/state/")
        assert response.status_code in (401, 403)

    def test_anonymous_warehouse_geographies_denied(self):
        response = self.anon.get("/api/warehouse/geographies/")
        assert response.status_code in (401, 403)
