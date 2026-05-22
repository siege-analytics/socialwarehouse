"""Tests for SW#22's NOMINATIM_URL env-driven Django setting.

The setting used to be a hardcoded ``"https://nominatim.openstreetmap.org/search?"``
(workspace-wide, no override). SW#22 made it env-overridable so the
self-hosted Nominatim profile (``docker-compose --profile geocoding``)
can route the geocode-addresses command at the in-cluster service.

The base URL ``NOMINATIM_URL`` is read from env; ``NOMINATIM_API_BASE_URL``
is built by appending ``/search?`` for back-compat with existing
consumers. These tests pin both shapes.
"""

from __future__ import annotations

import importlib
import os

import pytest


def _reload_settings_module():
    """Re-import the Django settings module under the current env.

    Settings modules read env at import time; we need a fresh import
    after monkeypatching the relevant variable.
    """
    import socialwarehouse.settings.base as base_settings
    return importlib.reload(base_settings)


class TestNominatimUrlDefault:
    """When NOMINATIM_URL is unset, the public endpoint is the default."""

    def test_default_url_is_public_nominatim(self, monkeypatch):
        monkeypatch.delenv("NOMINATIM_URL", raising=False)
        settings = _reload_settings_module()
        assert settings.NOMINATIM_URL == "https://nominatim.openstreetmap.org"

    def test_default_api_base_url_appends_search_path(self, monkeypatch):
        monkeypatch.delenv("NOMINATIM_URL", raising=False)
        settings = _reload_settings_module()
        assert settings.NOMINATIM_API_BASE_URL == "https://nominatim.openstreetmap.org/search?"


class TestNominatimUrlEnvOverride:
    """When NOMINATIM_URL is set in env, both NOMINATIM_URL and
    NOMINATIM_API_BASE_URL pick it up."""

    @pytest.mark.parametrize("env_value,expected_url,expected_api", [
        (
            "http://nominatim:8080",
            "http://nominatim:8080",
            "http://nominatim:8080/search?",
        ),
        (
            "http://localhost:8080",
            "http://localhost:8080",
            "http://localhost:8080/search?",
        ),
        # Trailing-slash on the env value should not produce a double-slash:
        (
            "http://nominatim:8080/",
            "http://nominatim:8080/",
            "http://nominatim:8080/search?",
        ),
    ])
    def test_env_value_flows_into_both_settings(self, monkeypatch, env_value, expected_url, expected_api):
        monkeypatch.setenv("NOMINATIM_URL", env_value)
        settings = _reload_settings_module()
        assert settings.NOMINATIM_URL == expected_url
        assert settings.NOMINATIM_API_BASE_URL == expected_api


class TestNominatimUserAgentEnvOverride:
    """SW#22 also made NOMINATIM_USER_AGENT env-overridable."""

    def test_default_user_agent(self, monkeypatch):
        monkeypatch.delenv("NOMINATIM_USER_AGENT", raising=False)
        settings = _reload_settings_module()
        assert settings.NOMINATIM_USER_AGENT == "socialwarehouse"

    def test_env_value_overrides_default(self, monkeypatch):
        monkeypatch.setenv("NOMINATIM_USER_AGENT", "socialwarehouse-self-host")
        settings = _reload_settings_module()
        assert settings.NOMINATIM_USER_AGENT == "socialwarehouse-self-host"
