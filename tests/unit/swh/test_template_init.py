"""Tests for ``swh init`` and ``swh/template.py`` (SW#308)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from django.test import SimpleTestCase

from swh.cli import cli
from swh.template import generate_env


class TestGenerateEnv(SimpleTestCase):
    """Unit tests for the .env template rendering."""

    def test_contains_required_vars(self):
        result = generate_env(project_name="test-proj", db_name="test_db")
        for var in [
            "POSTGRES_DB=test_db",
            "SW_PROJECT_NAME=test-proj",
            "DJANGO_SECRET_KEY=",
            "CELERY_BROKER_URL=",
        ]:
            self.assertIn(var, result)

    def test_secret_key_is_unique(self):
        env1 = generate_env()
        env2 = generate_env()
        key1 = _extract_var(env1, "DJANGO_SECRET_KEY")
        key2 = _extract_var(env2, "DJANGO_SECRET_KEY")
        self.assertNotEqual(key1, key2)

    def test_default_db_user_from_env(self):
        with patch.dict(os.environ, {"USER": "testrunner"}):
            result = generate_env()
            self.assertIn("POSTGRES_USER=testrunner", result)

    def test_custom_db_user(self):
        result = generate_env(db_user="custom_user")
        self.assertIn("POSTGRES_USER=custom_user", result)

    def test_custom_redis_url(self):
        result = generate_env(redis_url="redis://myredis:6380/1")
        self.assertIn("CELERY_BROKER_URL=redis://myredis:6380/1", result)

    def test_default_states(self):
        result = generate_env(default_states="48,06")
        self.assertIn("SW_DEFAULT_STATES=48,06", result)


class TestInitCommand(SimpleTestCase):
    """CLI integration tests for ``swh init``."""

    def test_init_writes_env_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("pyproject.toml").touch()
            result = runner.invoke(
                cli,
                ["init", "test-project", "--non-interactive", "--db-name", "test_db"],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            env_path = Path(".env")
            self.assertTrue(env_path.exists())
            content = env_path.read_text()
            self.assertIn("POSTGRES_DB=test_db", content)
            self.assertIn("SW_PROJECT_NAME=test-project", content)

    def test_init_skips_existing_env(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("pyproject.toml").touch()
            Path(".env").write_text("existing")
            result = runner.invoke(
                cli,
                ["init", "test-project", "--non-interactive"],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("already exists", result.output)
            self.assertEqual(Path(".env").read_text(), "existing")

    def test_init_shows_next_steps(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("pyproject.toml").touch()
            result = runner.invoke(
                cli,
                ["init", "--non-interactive"],
            )
            self.assertIn("Next steps", result.output)
            self.assertIn("swh doctor", result.output)


def _extract_var(env_text: str, var_name: str) -> str:
    for line in env_text.splitlines():
        if line.startswith(f"{var_name}="):
            return line.split("=", 1)[1]
    return ""
