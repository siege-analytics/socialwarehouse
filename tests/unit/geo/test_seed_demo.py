"""Tests for G.1 — seed_demo orchestration.

Mocks call_command so each sub-command is tracked but not actually
run. Pins: defaults (TX); --states multi-state ordering; --skip
domain filtering; --dry-run; unknown-skip rejection; per-state
sub-command sequence.
"""

from io import StringIO
from unittest.mock import patch, call

from django.core.management import call_command
from django.test import TestCase


class TestSeedDemoDefaults(TestCase):

    @patch("socialwarehouse.geo.management.commands.seed_demo.call_command")
    def test_default_is_texas_all_domains(self, mock_call):
        call_command("seed_demo", verbosity=0, stdout=StringIO())

        called_commands = [c.args[0] for c in mock_call.call_args_list]
        # Default = TX state, all 4 domains, all 6 commands (assign + acs + qcew + 3xnces).
        assert "assign_boundaries" in called_commands
        assert "load_acs" in called_commands
        assert "load_qcew" in called_commands
        assert "load_nces" in called_commands
        assert "load_nces_schools" in called_commands
        assert "load_nces_edge" in called_commands

    @patch("socialwarehouse.geo.management.commands.seed_demo.call_command")
    def test_default_state_is_tx(self, mock_call):
        call_command("seed_demo", verbosity=0, stdout=StringIO())

        # Every sub-command should have been called with state="48".
        for c in mock_call.call_args_list:
            assert c.kwargs.get("state") == "48", f"sub-command {c.args[0]} got state={c.kwargs.get('state')}"


class TestSeedDemoMultiState(TestCase):

    @patch("socialwarehouse.geo.management.commands.seed_demo.call_command")
    def test_multi_state_runs_each(self, mock_call):
        call_command("seed_demo", "--states=48,06", verbosity=0, stdout=StringIO())

        state_args = [c.kwargs.get("state") for c in mock_call.call_args_list]
        assert "48" in state_args
        assert "06" in state_args
        # And each appears at least once per domain (6 sub-commands x 2 states = 12 calls).
        assert state_args.count("48") == 6
        assert state_args.count("06") == 6


class TestSeedDemoSkip(TestCase):

    @patch("socialwarehouse.geo.management.commands.seed_demo.call_command")
    def test_skip_economic_and_civic(self, mock_call):
        call_command(
            "seed_demo", "--states=48", "--skip=economic,civic",
            verbosity=0, stdout=StringIO(),
        )

        called_commands = [c.args[0] for c in mock_call.call_args_list]
        # geo + demographic only; civic + economic skipped.
        assert "assign_boundaries" in called_commands
        assert "load_acs" in called_commands
        assert "load_qcew" not in called_commands
        assert "load_nces" not in called_commands
        assert "load_nces_schools" not in called_commands
        assert "load_nces_edge" not in called_commands

    def test_unknown_skip_reports_error(self):
        out = StringIO()
        call_command(
            "seed_demo", "--states=48", "--skip=invalid-domain",
            verbosity=0, stdout=out,
        )
        # The command writes an error and bails out without calling subcommands.
        assert "Unknown --skip values" in out.getvalue()


class TestSeedDemoDryRun(TestCase):

    @patch("socialwarehouse.geo.management.commands.seed_demo.call_command")
    def test_dry_run_calls_no_subcommands(self, mock_call):
        call_command(
            "seed_demo", "--states=48", "--dry-run",
            verbosity=0, stdout=StringIO(),
        )
        assert mock_call.call_count == 0


class TestSeedDemoErrorTolerance(TestCase):
    """A failing sub-command shouldn't abort the whole seed_demo run."""

    @patch("socialwarehouse.geo.management.commands.seed_demo.call_command")
    def test_one_failure_does_not_stop_others(self, mock_call):
        # Make load_acs fail.
        def side_effect(*args, **kwargs):
            if args[0] == "load_acs":
                raise RuntimeError("simulated Census API failure")

        mock_call.side_effect = side_effect

        # Should not raise; other commands should still be attempted.
        call_command("seed_demo", "--states=48", verbosity=0, stdout=StringIO())

        called_commands = [c.args[0] for c in mock_call.call_args_list]
        # Even with load_acs failing, downstream commands are still called.
        assert "load_qcew" in called_commands
        assert "load_nces" in called_commands
