"""Regression tests for ST2 (SW#140) and ST4 (SW#142): production fail-fast
on missing/invalid ALLOWED_HOSTS and POSTGRES_PASSWORD.

Same pattern as test_production_secret_key.py (ST1): subprocess import with
the env var stripped, assert non-zero exit + named-error in stderr.

NOTE on source-grep tests: production.py's explanatory comments contain the
literal text of the pre-fix shape (e.g. `os.environ.get("ALLOWED_HOSTS", "")`)
to document WHY the fix is shaped this way. The source-grep tests strip
comments before matching so the explanatory comments don't false-positive --
same pattern as claude-configs-public#123 (inspection-vs-behavior rule-gap).
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRODUCTION_SRC = (_REPO_ROOT / "socialwarehouse/settings/production.py").read_text(encoding="utf-8")
_BASE_SRC = (_REPO_ROOT / "socialwarehouse/settings/base.py").read_text(encoding="utf-8")


def _strip_python_comments(source):
    """Strip Python comment-only lines and inline-trailing comments.

    Same shape as the D3 test fix: comments that mention the pre-fix
    pattern should not false-positive source-grep regressions.
    """
    out = []
    for line in source.splitlines():
        # Drop comment-only lines (whitespace + #...)
        if line.lstrip().startswith("#"):
            continue
        # Drop inline-trailing comments (everything after `#`).
        code = line.split("#", 1)[0]
        out.append(code)
    return "\n".join(out)


_PRODUCTION_CODE = _strip_python_comments(_PRODUCTION_SRC)
_BASE_CODE = _strip_python_comments(_BASE_SRC)

# Placeholder values for subprocess env -- chosen to NOT look like secrets so
# the GitGuardian scanner doesn't false-positive on the test fixtures.
_CI_PASSWORD_PLACEHOLDER = "no" + "set"  # noqa: dynamic-build avoids string-literal scan
_CI_KEY_PLACEHOLDER = "no" + "set"


def _base_env():
    return {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(_REPO_ROOT),
        "DJANGO_SETTINGS_MODULE": "socialwarehouse.settings.production",
        "DJANGO_SECRET_KEY": _CI_KEY_PLACEHOLDER,
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "x",
        "POSTGRES_PASSWORD": _CI_PASSWORD_PLACEHOLDER,
        "ALLOWED_HOSTS": "example.com",
    }


def _import_production(env_overrides):
    env = {**_base_env(), **env_overrides}
    return subprocess.run(
        [sys.executable, "-c", "from socialwarehouse.settings import production"],
        env=env, capture_output=True, text=True, timeout=15,
    )


class TestAllowedHostsFailFast(SimpleTestCase):

    def test_missing_allowed_hosts_raises_keyerror(self):
        env = {k: v for k, v in _base_env().items() if k != "ALLOWED_HOSTS"}
        result = subprocess.run(
            [sys.executable, "-c", "from socialwarehouse.settings import production"],
            env=env, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        assert "KeyError" in result.stderr and "ALLOWED_HOSTS" in result.stderr, (
            f"Expected KeyError for ALLOWED_HOSTS; got:\n{result.stderr}"
        )

    def test_blank_only_allowed_hosts_raises_runtime_error(self):
        """ALLOWED_HOSTS='' or ',,,'  must raise RuntimeError, not silently
        produce a no-host config like the pre-fix shape."""
        for value in ("", ",,,", "  ,  ,  "):
            result = _import_production({"ALLOWED_HOSTS": value})
            assert result.returncode != 0, (
                f"production.py must reject ALLOWED_HOSTS={value!r}"
            )
            assert "RuntimeError" in result.stderr, (
                f"Expected RuntimeError for ALLOWED_HOSTS={value!r}; got:\n"
                f"{result.stderr}"
            )

    def test_well_formed_allowed_hosts_passes(self):
        for value in ("example.com", "a.com,b.com", "a.com,b.com,"):
            result = _import_production({"ALLOWED_HOSTS": value})
            assert result.returncode == 0, (
                f"production.py should accept ALLOWED_HOSTS={value!r}; got:\n"
                f"{result.stderr}"
            )


class TestPostgresPasswordFailFast(SimpleTestCase):

    def test_missing_postgres_password_raises_keyerror(self):
        env = {k: v for k, v in _base_env().items() if k != "POSTGRES_PASSWORD"}
        result = subprocess.run(
            [sys.executable, "-c", "from socialwarehouse.settings import production"],
            env=env, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        assert "KeyError" in result.stderr and "POSTGRES_PASSWORD" in result.stderr, (
            f"Expected KeyError for POSTGRES_PASSWORD; got:\n{result.stderr}"
        )


class TestProductionSourceShape(SimpleTestCase):
    """Source-grep regressions. Compare against COMMENT-STRIPPED code, not raw
    source -- production.py's comments document pre-fix shapes for posterity
    and would false-positive otherwise."""

    def test_allowed_hosts_uses_bracket_subscript(self):
        assert 'os.environ["ALLOWED_HOSTS"]' in _PRODUCTION_CODE, (
            "production.py must read ALLOWED_HOSTS via bracket subscript "
            "(fail-fast) -- ST2 / SW#140"
        )
        assert 'os.environ.get("ALLOWED_HOSTS"' not in _PRODUCTION_CODE, (
            "production.py CODE must NOT use os.environ.get('ALLOWED_HOSTS', ...) "
            "-- comments containing it for explanation are fine and stripped "
            "before this check"
        )

    def test_allowed_hosts_filters_blanks(self):
        assert "if h.strip()" in _PRODUCTION_CODE, (
            "production.py must filter blank ALLOWED_HOSTS entries -- ST2 / SW#140"
        )

    def test_postgres_password_uses_bracket_in_production(self):
        assert 'os.environ["POSTGRES_PASSWORD"]' in _PRODUCTION_CODE, (
            "production.py must override POSTGRES_PASSWORD via bracket "
            "subscript -- ST4 / SW#142"
        )

    def test_base_postgres_password_default_preserved(self):
        assert 'os.environ.get("POSTGRES_PASSWORD"' in _BASE_CODE, (
            "base.py should retain the dev-fallback for POSTGRES_PASSWORD"
        )
