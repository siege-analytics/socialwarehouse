"""Tests for D Phase 3 (SW#192): load_decennial.

Mocks siege_utilities.geo.census.CensusAPI. Pins:
- Default-variables path (uses curated PL catalog when --variables omitted)
- Happy-path row-to-DecennialCount conversion
- Jam-value annotation
- update_or_create idempotency
- Unknown-vintage CommandError
- --dry-run no-write
"""

from io import StringIO
from unittest.mock import patch, MagicMock

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadDecennialTestBase(TestCase):

    def setUp(self):
        from socialwarehouse.demographic.models import DecennialVariable
        from socialwarehouse.geo.models import CensusDecadalVintage

        self.vintage = CensusDecadalVintage.objects.filter(year=2020).first()
        if self.vintage is None:
            from datetime import date
            self.vintage = CensusDecadalVintage.objects.create(
                year=2020,
                effective_from=date(2020, 4, 1),
                effective_to=date(2030, 4, 1),
            )
        self.var_total = DecennialVariable.objects.get(variable_code="P1_001N")
        self.var_white = DecennialVariable.objects.get(variable_code="P1_003N")

    def _df(self, rows):
        return pd.DataFrame(rows)


class TestLoadDecennialHappyPath(LoadDecennialTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_writes_count_per_row_per_variable(self, mock_api_class):
        from socialwarehouse.demographic.models import DecennialCount

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._df([
            {"GEOID": "06037", "NAME": "Los Angeles County",
             "P1_001N": "10014009", "P1_003N": "2616720"},
            {"GEOID": "06075", "NAME": "San Francisco County",
             "P1_001N": "873965", "P1_003N": "354935"},
        ])
        mock_api_class.return_value = mock_api

        call_command(
            "load_decennial",
            f"--vintage={self.vintage.name}",
            "--state=06", "--geography=county",
            "--variables=P1_001N,P1_003N",
            verbosity=0,
        )

        rows = DecennialCount.objects.filter(vintage=self.vintage)
        assert rows.count() == 4
        la_total = rows.get(variable=self.var_total, geoid="06037")
        assert la_total.value == 10014009
        assert la_total.annotation == ""
        sf_white = rows.get(variable=self.var_white, geoid="06075")
        assert sf_white.value == 354935


class TestLoadDecennialAnnotations(LoadDecennialTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_jam_value_stored_in_annotation(self, mock_api_class):
        from socialwarehouse.demographic.models import DecennialCount

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._df([
            {"GEOID": "06037", "P1_001N": "*"},
        ])
        mock_api_class.return_value = mock_api

        call_command(
            "load_decennial", f"--vintage={self.vintage.name}",
            "--state=06", "--geography=county", "--variables=P1_001N",
            verbosity=0,
        )

        c = DecennialCount.objects.get(variable=self.var_total, geoid="06037")
        assert c.value is None
        assert c.annotation == "*"


class TestLoadDecennialDefaultVariables(LoadDecennialTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_default_uses_pl_catalog(self, mock_api_class):
        from socialwarehouse.demographic.models import DecennialVariable

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._df([{"GEOID": "06"}])
        mock_api_class.return_value = mock_api

        call_command(
            "load_decennial", f"--vintage={self.vintage.name}",
            "--state=06", "--geography=state", verbosity=0,
        )

        called = mock_api.fetch_data.call_args.kwargs["variables"]
        pl_codes = set(
            DecennialVariable.objects.filter(dataset="pl")
            .values_list("variable_code", flat=True)
        )
        assert set(called) == pl_codes
        # PL dataset is requested by full path, not just 'pl'.
        assert mock_api.fetch_data.call_args.kwargs["dataset"] == "dec/pl"


class TestLoadDecennialIdempotent(LoadDecennialTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_rerun_overwrites(self, mock_api_class):
        from socialwarehouse.demographic.models import DecennialCount

        mock_api = MagicMock()
        mock_api_class.return_value = mock_api

        mock_api.fetch_data.return_value = self._df([
            {"GEOID": "06037", "P1_001N": "10000000"},
        ])
        call_command("load_decennial", f"--vintage={self.vintage.name}",
                     "--state=06", "--geography=county",
                     "--variables=P1_001N", verbosity=0)

        mock_api.fetch_data.return_value = self._df([
            {"GEOID": "06037", "P1_001N": "10014009"},
        ])
        call_command("load_decennial", f"--vintage={self.vintage.name}",
                     "--state=06", "--geography=county",
                     "--variables=P1_001N", verbosity=0)

        rows = DecennialCount.objects.filter(variable=self.var_total, geoid="06037")
        assert rows.count() == 1
        assert rows.first().value == 10014009


class TestLoadDecennialValidation(LoadDecennialTestBase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command("load_decennial", "--vintage=NOT-A-VINTAGE",
                         "--state=06", "--geography=county", verbosity=0)
        assert "No CensusDecadalVintage" in str(cm.exception)


class TestLoadDecennialDryRun(LoadDecennialTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_dry_run_no_writes(self, mock_api_class):
        from socialwarehouse.demographic.models import DecennialCount

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._df([
            {"GEOID": "06037", "P1_001N": "10014009"},
        ])
        mock_api_class.return_value = mock_api

        before = DecennialCount.objects.count()
        call_command("load_decennial", f"--vintage={self.vintage.name}",
                     "--state=06", "--geography=county",
                     "--variables=P1_001N", "--dry-run",
                     verbosity=0, stdout=StringIO())
        assert DecennialCount.objects.count() == before
