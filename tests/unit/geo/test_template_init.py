"""Tests for G.2 — template_init setup wizard.

Mocks call_command + filesystem so tests don't touch real state.
Covers non-interactive mode (the scripted-CI path); interactive
mode would need stdin mocking which adds noise without much value.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase, override_settings


class TestTemplateInitNonInteractive(TestCase):

    def _tmp_base(self, tmp_path):
        """Return an override_settings with BASE_DIR=tmp_path."""
        return override_settings(BASE_DIR=str(tmp_path))

    @patch("socialwarehouse.geo.management.commands.template_init.call_command")
    def test_writes_env_when_missing(self, mock_call):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self._tmp_base(tmp_path):
                call_command(
                    "template_init", "--non-interactive",
                    "--states=48", "--project-name=test-warehouse",
                    "--db-name=test_db",
                    verbosity=0,
                )

            env_path = tmp_path / ".env"
            assert env_path.exists()
            content = env_path.read_text()
            assert "DJANGO_SECRET_KEY=" in content
            assert "POSTGRES_DB=test_db" in content
            assert "SW_PROJECT_NAME=test-warehouse" in content
            assert "SW_DEFAULT_STATES=48" in content

    @patch("socialwarehouse.geo.management.commands.template_init.call_command")
    def test_skips_env_when_exists(self, mock_call):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            env_path.write_text("PRESERVED=yes\n")
            original_size = env_path.stat().st_size

            with self._tmp_base(tmp_path):
                call_command(
                    "template_init", "--non-interactive",
                    "--states=48", "--project-name=test",
                    verbosity=0,
                )

            assert env_path.read_text() == "PRESERVED=yes\n"
            assert env_path.stat().st_size == original_size

    @patch("socialwarehouse.geo.management.commands.template_init.call_command")
    def test_runs_migrate_and_seed_by_default(self, mock_call):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self._tmp_base(Path(tmp)):
                call_command(
                    "template_init", "--non-interactive",
                    "--states=48", verbosity=0,
                )

            commands_called = [c.args[0] for c in mock_call.call_args_list]
            assert "migrate" in commands_called
            assert "seed_demo" in commands_called

    @patch("socialwarehouse.geo.management.commands.template_init.call_command")
    def test_skip_migrate_and_skip_seed(self, mock_call):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self._tmp_base(Path(tmp)):
                call_command(
                    "template_init", "--non-interactive",
                    "--states=48", "--skip-migrate", "--skip-seed",
                    verbosity=0,
                )

            assert mock_call.call_count == 0

    @patch("socialwarehouse.geo.management.commands.template_init.call_command")
    def test_seed_demo_failure_does_not_abort(self, mock_call):
        """If seed_demo throws, template_init logs and continues to the
        final-guidance step rather than crashing.
        """
        import tempfile

        def side_effect(*args, **kwargs):
            if args[0] == "seed_demo":
                raise RuntimeError("simulated seed failure")

        mock_call.side_effect = side_effect

        with tempfile.TemporaryDirectory() as tmp:
            with self._tmp_base(Path(tmp)):
                # Should not raise.
                call_command(
                    "template_init", "--non-interactive",
                    "--states=48", verbosity=0,
                )

    @patch("socialwarehouse.geo.management.commands.template_init.call_command")
    def test_migrate_failure_aborts_before_seed(self, mock_call):
        """A migrate failure should abort before seed_demo runs."""
        import tempfile

        def side_effect(*args, **kwargs):
            if args[0] == "migrate":
                raise RuntimeError("simulated migrate failure")

        mock_call.side_effect = side_effect

        with tempfile.TemporaryDirectory() as tmp:
            with self._tmp_base(Path(tmp)):
                call_command(
                    "template_init", "--non-interactive",
                    "--states=48", verbosity=0,
                )

            # migrate was attempted; seed_demo was NOT (early return).
            commands_called = [c.args[0] for c in mock_call.call_args_list]
            assert "migrate" in commands_called
            assert "seed_demo" not in commands_called
