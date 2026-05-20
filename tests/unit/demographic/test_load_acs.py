"""Tests for D Phase 1b (SW#192): load_acs command.

Mocks siege_utilities.geo.census.CensusAPI so tests don't hit the
network. Pins the row-to-ACSEstimate conversion contract (GEOID
extraction, value/MOE parsing, jam-value annotation) and the
vintage / variable lookup behavior.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch, MagicMock

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadACSTestBase(TestCase):
    """Shared setup: real ACSVintage (seeded by migrations) + real ACSVariable
    rows + a mocked SU CensusAPI."""

    def setUp(self):
        from socialwarehouse.demographic.models import ACSVariable
        from socialwarehouse.geo.models import ACSVintage

        self.vintage = ACSVintage.objects.filter(span_years=5).order_by("-end_year").first()
        assert self.vintage is not None, "ACSVintage 5-year rows seeded by migration 0004"
        self.var_pop = ACSVariable.objects.get(variable_code="B01001_001E")
        self.var_income = ACSVariable.objects.get(variable_code="B19013_001E")

    def _mocked_fetch_df(self, rows):
        """Build a DataFrame in SU CensusAPI's post-processed shape."""
        return pd.DataFrame(rows)


class TestLoadACSHappyPath(LoadACSTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_writes_estimate_per_row_per_variable(self, mock_api_class):
        from socialwarehouse.demographic.models import ACSEstimate

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._mocked_fetch_df([
            {"GEOID": "06037103300", "NAME": "Census Tract 1033, LA County",
             "B01001_001E": "4123", "B01001_001M": "129",
             "B19013_001E": "78421", "B19013_001M": "5234"},
            {"GEOID": "06037103400", "NAME": "Census Tract 1034, LA County",
             "B01001_001E": "3812", "B01001_001M": "143",
             "B19013_001E": "65800", "B19013_001M": "4112"},
        ])
        mock_api_class.return_value = mock_api

        call_command(
            "load_acs",
            f"--vintage={self.vintage.name}",
            "--state=06",
            "--geography=tract",
            "--variables=B01001_001E,B19013_001E",
            verbosity=0,
        )

        rows = ACSEstimate.objects.filter(vintage=self.vintage)
        assert rows.count() == 4
        pop_1033 = rows.get(variable=self.var_pop, geoid="06037103300")
        assert pop_1033.value == Decimal("4123")
        assert pop_1033.moe == Decimal("129")
        assert pop_1033.annotation == ""
        income_1034 = rows.get(variable=self.var_income, geoid="06037103400")
        assert income_1034.value == Decimal("65800")
        assert income_1034.moe == Decimal("4112")


class TestLoadACSAnnotations(LoadACSTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_jam_value_stored_in_annotation(self, mock_api_class):
        from socialwarehouse.demographic.models import ACSEstimate

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._mocked_fetch_df([
            {"GEOID": "06037103300", "B19013_001E": "*", "B19013_001M": None},
        ])
        mock_api_class.return_value = mock_api

        call_command(
            "load_acs",
            f"--vintage={self.vintage.name}",
            "--state=06",
            "--geography=tract",
            "--variables=B19013_001E",
            verbosity=0,
        )

        e = ACSEstimate.objects.get(variable=self.var_income, geoid="06037103300")
        assert e.value is None
        assert e.annotation == "*"
        assert e.moe is None


class TestLoadACSDefaultVariables(LoadACSTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_uses_catalog_when_variables_not_passed(self, mock_api_class):
        """If --variables omitted, the command uses every ACSVariable in the catalog."""
        from socialwarehouse.demographic.models import ACSVariable

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._mocked_fetch_df([
            {"GEOID": "06"},
        ])
        mock_api_class.return_value = mock_api

        call_command(
            "load_acs",
            f"--vintage={self.vintage.name}",
            "--state=06",
            "--geography=state",
            verbosity=0,
        )

        # The DataFrame doesn't carry any of the catalog values, so all
        # ACSEstimate rows have value=None — but every catalog var was
        # *attempted*. Check fetch_data was called with the catalog list.
        called_vars = mock_api.fetch_data.call_args.kwargs["variables"]
        assert set(called_vars) == set(
            ACSVariable.objects.values_list("variable_code", flat=True)
        )


class TestLoadACSIdempotent(LoadACSTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_rerun_overwrites_not_duplicates(self, mock_api_class):
        from socialwarehouse.demographic.models import ACSEstimate

        first_run = self._mocked_fetch_df([
            {"GEOID": "06037103300", "B01001_001E": "4000", "B01001_001M": "100"},
        ])
        second_run = self._mocked_fetch_df([
            {"GEOID": "06037103300", "B01001_001E": "4123", "B01001_001M": "129"},
        ])

        mock_api = MagicMock()
        mock_api_class.return_value = mock_api

        mock_api.fetch_data.return_value = first_run
        call_command("load_acs", f"--vintage={self.vintage.name}", "--state=06",
                     "--geography=tract", "--variables=B01001_001E", verbosity=0)

        mock_api.fetch_data.return_value = second_run
        call_command("load_acs", f"--vintage={self.vintage.name}", "--state=06",
                     "--geography=tract", "--variables=B01001_001E", verbosity=0)

        rows = ACSEstimate.objects.filter(variable=self.var_pop, geoid="06037103300")
        assert rows.count() == 1
        assert rows.first().value == Decimal("4123")


class TestLoadACSValidation(LoadACSTestBase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command(
                "load_acs", "--vintage=NOT-A-REAL-VINTAGE", "--state=06",
                "--geography=tract", verbosity=0,
            )
        assert "No ACSVintage" in str(cm.exception)


class TestLoadACSDryRun(LoadACSTestBase):

    @patch("siege_utilities.geo.census.CensusAPI")
    def test_dry_run_does_not_write(self, mock_api_class):
        from socialwarehouse.demographic.models import ACSEstimate

        mock_api = MagicMock()
        mock_api.fetch_data.return_value = self._mocked_fetch_df([
            {"GEOID": "06037103300", "B01001_001E": "4123", "B01001_001M": "129"},
        ])
        mock_api_class.return_value = mock_api

        before = ACSEstimate.objects.count()
        call_command(
            "load_acs", f"--vintage={self.vintage.name}", "--state=06",
            "--geography=tract", "--variables=B01001_001E", "--dry-run",
            verbosity=0, stdout=StringIO(),
        )
        assert ACSEstimate.objects.count() == before
