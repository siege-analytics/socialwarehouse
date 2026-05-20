"""Regression test for S5 (SW#135): swh.cli no longer reconfigures
the host process's root logger as a side effect of import.

Behavior test (writing-tests:6): runs a subprocess that installs a
sentinel handler on the root logger BEFORE importing swh.cli. If
basicConfig still runs at import time, the sentinel handler is
displaced and `force=False` would otherwise have no effect, but
basicConfig with default args replaces handlers on a previously
unconfigured root logger. The assertion is that the sentinel survives.
"""

import os
import subprocess
import sys

from django.test import SimpleTestCase


_PROBE = r"""
import logging
root = logging.getLogger()
sentinel = logging.NullHandler()
root.addHandler(sentinel)
import swh.cli  # noqa: F401
assert sentinel in root.handlers, "import of swh.cli displaced sentinel handler"
print("OK")
"""


class TestCliImportDoesNotReconfigureRootLogger(SimpleTestCase):

    def test_import_does_not_displace_sentinel_handler(self):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "DJANGO_SETTINGS_MODULE": "socialwarehouse.settings.base",
            "DJANGO_SECRET_KEY": "test",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "x",
            "POSTGRES_PASSWORD": "test",
            "ALLOWED_HOSTS": "localhost",
            "SW_WAREHOUSE_ROOT": "file:///tmp/sw-warehouse",
        }
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "OK" in result.stdout
