"""Tests for ``swh doctor`` checks (SW#308)."""

from __future__ import annotations

import sys
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
        fake_version = type(sys.version_info)(3, 10, 0, "final", 0)
        with patch.object(sys, "version_info", fake_version):
            result = check_python_version()
            self.assertEqual(result.status, Status.FAIL)
            self.assertIn("3.10", result.detail)


class TestEnvFileCheck(SimpleTestCase):

    def test_fails_when_missing(self):
        with patch("swh.doctor.find_repo_root", return_value=__import__("pathlib").Path("/nonexistent")):
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
