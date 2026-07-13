"""Tests for ``swh.config.NominatimSettings`` (NOMINATIM_* env-driven config).

Nominatim client config is a pydantic-settings class in ``swh/config.py``
with ``env_prefix="NOMINATIM_"``: it defaults to the public OSM instance
and is overridable for the self-hosted geocoding profile
(``docker-compose --profile geocoding``).

This supersedes SW#22's original Django-settings shape — the config moved
to ``swh.config`` (pydantic settings), and the ``/search?`` path is
appended by the geocoder at call time rather than stored on the settings
object, so there is no longer a ``NOMINATIM_API_BASE_URL`` setting.
"""
from __future__ import annotations

from swh.config import NominatimSettings


class TestNominatimSettingsDefault:
    """With no env override, the public OSM endpoint is the default."""

    def test_default_url_is_public_nominatim(self, monkeypatch):
        monkeypatch.delenv("NOMINATIM_URL", raising=False)
        assert NominatimSettings().url == "https://nominatim.openstreetmap.org"

    def test_default_user_agent(self, monkeypatch):
        monkeypatch.delenv("NOMINATIM_USER_AGENT", raising=False)
        assert NominatimSettings().user_agent == "socialwarehouse"


class TestNominatimSettingsEnvOverride:
    """NOMINATIM_URL / NOMINATIM_USER_AGENT env vars override the defaults."""

    def test_url_env_override(self, monkeypatch):
        monkeypatch.setenv("NOMINATIM_URL", "http://nominatim:8080")
        assert NominatimSettings().url == "http://nominatim:8080"

    def test_user_agent_env_override(self, monkeypatch):
        monkeypatch.setenv("NOMINATIM_USER_AGENT", "socialwarehouse-self-host")
        assert NominatimSettings().user_agent == "socialwarehouse-self-host"
