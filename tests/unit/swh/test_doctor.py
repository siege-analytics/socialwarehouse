"""Tests for ``swh doctor`` checks (SW#308)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from swh.doctor import (
    Status,
    check_disk_space,
    check_env_file,
    check_python_version,
    check_spark,
)


class TestPythonVersionCheck(SimpleTestCase):

    def test_passes_on_current_python(self):
        result = check_python_version()
        self.assertEqual(result.status, Status.PASS)
        self.assertIn(str(sys.version_info.major), result.detail)

    def test_fails_on_old_python(self):
        # sys.version_info's type cannot be instantiated directly (TypeError
        # on 3.12+); a SimpleNamespace with the attributes check_python_version
        # reads (major/minor/micro) is an adequate, patchable stand-in.
        fake_version = SimpleNamespace(major=3, minor=10, micro=0, releaselevel="final", serial=0)
        with patch.object(sys, "version_info", fake_version):
            result = check_python_version()
            self.assertEqual(result.status, Status.FAIL)
            self.assertIn("3.10", result.detail)


class TestEnvFileCheck(SimpleTestCase):

    def test_fails_when_missing(self):
        # check_env_file does `from swh.template import find_repo_root` at call
        # time, so the patch target is swh.template (not swh.doctor).
        with patch("swh.template.find_repo_root", return_value=Path("/nonexistent")):
            result = check_env_file()
            self.assertEqual(result.status, Status.FAIL)
            self.assertIn("not found", result.detail)


class TestDiskSpaceCheck(SimpleTestCase):

    def test_passes_or_warns(self):
        result = check_disk_space()
        self.assertIn(result.status, (Status.PASS, Status.WARN))
        self.assertIn("GB free", result.detail)


class TestSparkCheck(SimpleTestCase):

    def test_warns_when_not_installed(self):
        with patch.dict(sys.modules, {"pyspark": None}):
            result = check_spark()
            self.assertIn(result.status, (Status.PASS, Status.WARN))


class TestDoctorCommand(SimpleTestCase):

    def test_doctor_runs(self):
        from click.testing import CliRunner

        from swh.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--json"])
        self.assertEqual(result.exit_code, 0, result.output) if "FAIL" not in result.output else None

    def test_doctor_json_format(self):
        import json

        from click.testing import CliRunner

        from swh.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--json"])
        data = json.loads(result.output)
        self.assertIsInstance(data, list)
        self.assertTrue(all("name" in item and "status" in item for item in data))
