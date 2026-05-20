"""Regression test for ST3 (SW#141): GST sys.path wiring in
socialwarehouse/settings/base.py so every entry point (manage / wsgi /
asgi / pytest / direct-import) gets the GST app dir on sys.path.

Pre-fix the insert lived only in manage.py; non-manage entry points
hit ModuleNotFoundError on `import locations` at startup.

Subprocess imports settings.base in an env-stripped subprocess and
asserts sys.path contains the GST app dir after.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BASE_SRC = (_REPO_ROOT / "socialwarehouse/settings/base.py").read_text(encoding="utf-8")
_MANAGE_SRC = (_REPO_ROOT / "manage.py").read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = [line.split("#", 1)[0] for line in cleaned.splitlines()]
    return "\n".join(out)


_BASE_CODE = _strip_comments_and_docstrings(_BASE_SRC)
_MANAGE_CODE = _strip_comments_and_docstrings(_MANAGE_SRC)


class TestBaseSettingsInsertsGstPath(SimpleTestCase):
    """Source-grep: base.py must contain a sys.path.insert for the GST
    app dir before INSTALLED_APPS is referenced."""

    def test_base_imports_sys(self):
        assert "import sys" in _BASE_CODE, (
            "base.py must import sys to manipulate sys.path (ST3 / SW#141)"
        )

    def test_base_inserts_gst_app_dir(self):
        # Look for sys.path.insert with a path containing
        # vendor/geodjango_simple_template.
        assert "sys.path.insert" in _BASE_CODE, (
            "base.py must call sys.path.insert for GST submodule "
            "(ST3 / SW#141)"
        )
        assert "geodjango_simple_template" in _BASE_CODE, (
            "base.py's sys.path insert must target the GST submodule path"
        )

    def test_insert_runs_before_installed_apps_reference(self):
        # INSTALLED_APPS = [...] line must come after the sys.path insert.
        lines = _BASE_CODE.splitlines()
        installed_idx = next(
            (i for i, l in enumerate(lines) if l.startswith("INSTALLED_APPS")),
            None,
        )
        insert_idx = next(
            (i for i, l in enumerate(lines) if "sys.path.insert" in l),
            None,
        )
        assert installed_idx is not None and insert_idx is not None
        assert insert_idx < installed_idx, (
            f"sys.path.insert (line {insert_idx}) must precede "
            f"INSTALLED_APPS (line {installed_idx}); otherwise Django "
            f"processes INSTALLED_APPS before sys.path is updated."
        )


class TestSubprocessImportInjectsPath(SimpleTestCase):
    """Behavior test: a fresh subprocess that imports settings.base
    should have the GST app dir on sys.path after the import."""

    def test_direct_settings_import_inserts_gst_path(self):
        # Spawn a clean Python subprocess, import settings.base directly,
        # then print sys.path entries that look like the GST app dir.
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_REPO_ROOT),
            "DJANGO_SETTINGS_MODULE": "socialwarehouse.settings.base",
            # Provide the env vars base.py reads.
            "DJANGO_SECRET_KEY": "test",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "x",
            "ALLOWED_HOSTS": "localhost",
        }
        script = (
            "from socialwarehouse.settings import base; "
            "import sys; "
            "import json; "
            "print(json.dumps([p for p in sys.path if 'hellodjango' in p]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            env=env, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, (
            f"Subprocess failed: stderr={result.stderr!r}"
        )
        # Parse JSON from stdout; the LAST line is our print.
        import json
        # Take the last non-empty line.
        last = [l for l in result.stdout.strip().splitlines() if l.strip()][-1]
        gst_paths = json.loads(last)
        assert gst_paths, (
            "After importing settings.base, sys.path must contain an "
            "entry ending in '.../hellodjango'. Got: "
            + repr(result.stdout)
        )
