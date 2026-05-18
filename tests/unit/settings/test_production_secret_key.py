"""Regression test for ST1 (SW#139): production.py fails fast on missing DJANGO_SECRET_KEY.

Pre-fix: base.py's SECRET_KEY default was 'insecure-dev-key-change-in-production'
and production.py inherited it via wildcard import. A production deployment
that forgot to set DJANGO_SECRET_KEY silently ran with the insecure key.

Post-fix: production.py does SECRET_KEY = os.environ["DJANGO_SECRET_KEY"],
which raises KeyError at module-load if the env var is unset.

Test strategy: import production.py in a subprocess with DJANGO_SECRET_KEY
unset and assert KeyError. base.py's dev fallback is preserved (separate
test confirms it).
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRODUCTION_SRC = (_REPO_ROOT / "socialwarehouse/settings/production.py").read_text(encoding="utf-8")
_BASE_SRC = (_REPO_ROOT / "socialwarehouse/settings/base.py").read_text(encoding="utf-8")


class TestProductionFailFastOnMissingSecretKey(SimpleTestCase):
    """ST1 fix: production.py raises KeyError when DJANGO_SECRET_KEY is unset."""

    def test_production_imports_fail_on_missing_secret_key(self):
        """Spawn a subprocess that imports production settings with the env
        var unset and assert KeyError.

        Uses subprocess (not pytest's monkeypatch) so Django's settings cache
        and any other process-level state stays clean. Stripping the env var
        in-process and re-importing is fragile.
        """
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_SECRET_KEY"}
        env["DJANGO_SETTINGS_MODULE"] = "socialwarehouse.settings.production"
        env["PYTHONPATH"] = str(_REPO_ROOT)
        # Force-set a few env vars that base.py reads so failure is isolated
        # to SECRET_KEY's KeyError (not e.g. POSTGRES_DB being missing).
        env.setdefault("POSTGRES_DB", "x")
        env.setdefault("POSTGRES_USER", "x")
        env.setdefault("ALLOWED_HOSTS", "localhost")

        result = subprocess.run(
            [sys.executable, "-c", "from socialwarehouse.settings import production"],
            env=env, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0, (
            "production.py must fail when DJANGO_SECRET_KEY is unset "
            "(ST1 / SW#139). Got returncode 0."
        )
        assert "KeyError" in result.stderr and "DJANGO_SECRET_KEY" in result.stderr, (
            f"Expected KeyError mentioning DJANGO_SECRET_KEY in stderr; got:\n"
            f"{result.stderr}"
        )


class TestProductionSourceShape(SimpleTestCase):
    """Source-grep regressions: red on revert of the fail-fast pattern."""

    def test_production_uses_bracket_subscript(self):
        """Post-fix production.py must use os.environ['DJANGO_SECRET_KEY']
        (raises KeyError) NOT os.environ.get(...) (silently returns None or
        a default)."""
        assert 'os.environ["DJANGO_SECRET_KEY"]' in _PRODUCTION_SRC, (
            "production.py must set SECRET_KEY via os.environ['DJANGO_SECRET_KEY'] "
            "for fail-fast (ST1 / SW#139)"
        )
        # The buggy shape -- silent default -- is the regression target.
        assert 'os.environ.get("DJANGO_SECRET_KEY"' not in _PRODUCTION_SRC, (
            "production.py must NOT use os.environ.get('DJANGO_SECRET_KEY', ...) "
            "-- that silently inherits the insecure base.py default"
        )

    def test_base_dev_fallback_preserved(self):
        """base.py still has a dev-only fallback so local development works
        without setting the env var. Production overrides it."""
        assert 'os.environ.get("DJANGO_SECRET_KEY"' in _BASE_SRC, (
            "base.py should retain the dev-only fallback for local development; "
            "production.py overrides it with fail-fast bracket access"
        )
