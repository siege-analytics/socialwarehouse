"""Regression tests for ST2 (SW#140) and ST4 (SW#142): production fail-fast
on missing/invalid ALLOWED_HOSTS and POSTGRES_PASSWORD.

Same pattern as test_production_secret_key.py (ST1): subprocess import with
the env var stripped, assert non-zero exit + named-error in stderr.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRODUCTION_SRC = (_REPO_ROOT / "socialwarehouse/settings/production.py").read_text(encoding="utf-8")
_BASE_SRC = (_REPO_ROOT / "socialwarehouse/settings/base.py").read_text(encoding="utf-8")


def _import_production(env_overrides):
    """Spawn a subprocess that imports production with the given env vars set.

    `env_overrides` is merged into a minimal clean env. Returns CompletedProcess.
    """
    base_env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(_REPO_ROOT),
        "DJANGO_SETTINGS_MODULE": "socialwarehouse.settings.production",
        # Set known-good defaults for the env vars NOT under test in this run.
        "DJANGO_SECRET_KEY": "test-key",
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "x",
        "POSTGRES_PASSWORD": "test-pw",
        "ALLOWED_HOSTS": "example.com",
    }
    env = {**base_env, **env_overrides}
    return subprocess.run(
        [sys.executable, "-c", "from socialwarehouse.settings import production"],
        env=env, capture_output=True, text=True, timeout=15,
    )


class TestAllowedHostsFailFast(SimpleTestCase):

    def test_missing_allowed_hosts_raises_keyerror(self):
        env = {}
        env_with_unset = {k: v for k, v in {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_REPO_ROOT),
            "DJANGO_SETTINGS_MODULE": "socialwarehouse.settings.production",
            "DJANGO_SECRET_KEY": "test-key",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "x",
            "POSTGRES_PASSWORD": "test-pw",
        }.items()}
        result = subprocess.run(
            [sys.executable, "-c", "from socialwarehouse.settings import production"],
            env=env_with_unset, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        assert "KeyError" in result.stderr and "ALLOWED_HOSTS" in result.stderr, (
            f"Expected KeyError for ALLOWED_HOSTS; got:\n{result.stderr}"
        )

    def test_blank_only_allowed_hosts_raises_runtime_error(self):
        """ALLOWED_HOSTS='' or ALLOWED_HOSTS=',,,' must raise RuntimeError,
        not silently produce a no-host config like the pre-fix [\"\"] shape."""
        for value in ("", ",,,", "  ,  ,  "):
            result = _import_production({"ALLOWED_HOSTS": value})
            assert result.returncode != 0, (
                f"production.py must reject ALLOWED_HOSTS={value!r} "
                f"(no actual hosts)"
            )
            assert "RuntimeError" in result.stderr, (
                f"Expected RuntimeError for ALLOWED_HOSTS={value!r}; got:\n"
                f"{result.stderr}"
            )

    def test_well_formed_allowed_hosts_passes(self):
        # Sanity-check: a normal value imports cleanly. Trailing-comma form
        # supported (filtered).
        for value in ("example.com", "a.com,b.com", "a.com,b.com,"):
            result = _import_production({"ALLOWED_HOSTS": value})
            assert result.returncode == 0, (
                f"production.py should accept ALLOWED_HOSTS={value!r}; got:\n"
                f"{result.stderr}"
            )


class TestPostgresPasswordFailFast(SimpleTestCase):

    def test_missing_postgres_password_raises_keyerror(self):
        env_with_unset = {k: v for k, v in {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_REPO_ROOT),
            "DJANGO_SETTINGS_MODULE": "socialwarehouse.settings.production",
            "DJANGO_SECRET_KEY": "test-key",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "x",
            "ALLOWED_HOSTS": "example.com",
        }.items()}
        result = subprocess.run(
            [sys.executable, "-c", "from socialwarehouse.settings import production"],
            env=env_with_unset, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        assert "KeyError" in result.stderr and "POSTGRES_PASSWORD" in result.stderr, (
            f"Expected KeyError for POSTGRES_PASSWORD; got:\n{result.stderr}"
        )


class TestProductionSourceShape(SimpleTestCase):

    def test_allowed_hosts_uses_bracket_subscript(self):
        assert 'os.environ["ALLOWED_HOSTS"]' in _PRODUCTION_SRC, (
            "production.py must read ALLOWED_HOSTS via bracket subscript "
            "(fail-fast) -- ST2 / SW#140"
        )
        assert 'os.environ.get("ALLOWED_HOSTS"' not in _PRODUCTION_SRC, (
            "production.py must NOT use os.environ.get('ALLOWED_HOSTS', ...) "
            "-- that silently returns [''] when unset"
        )

    def test_allowed_hosts_filters_blanks(self):
        assert "if h.strip()" in _PRODUCTION_SRC, (
            "production.py must filter blank ALLOWED_HOSTS entries "
            "(supports trailing-comma form) -- ST2 / SW#140"
        )

    def test_postgres_password_uses_bracket_in_production(self):
        assert 'os.environ["POSTGRES_PASSWORD"]' in _PRODUCTION_SRC, (
            "production.py must override POSTGRES_PASSWORD via bracket "
            "subscript -- ST4 / SW#142"
        )

    def test_base_postgres_password_default_preserved(self):
        # Dev ergonomics: base.py retains the empty-string default so local
        # dev doesn't require POSTGRES_PASSWORD to be set.
        assert 'os.environ.get("POSTGRES_PASSWORD"' in _BASE_SRC, (
            "base.py should retain the dev-fallback for POSTGRES_PASSWORD"
        )
