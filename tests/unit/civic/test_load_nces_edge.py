"""Tests for F Phase 1c: NCESDistrictEDGEDemographics + load_nces_edge.

Mocks NCESFiles.load_edge_district_demographics. Pins: happy path,
state filter, poverty rate computation, negative-sentinel handling,
unknown vintage, dry-run.
"""

from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadEDGETestBase(TestCase):

    def setUp(self):
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        self.vintage = NCESSchoolYearVintage.objects.filter(start_year=2022, end_year=2023).first()
        if self.vintage is None:
            self.vintage = NCESSchoolYearVintage.objects.create(
                start_year=2022, end_year=2023,
                effective_from=date(2022, 8, 1), effective_to=date(2023, 8, 1),
            )


class TestLoadEDGEHappyPath(LoadEDGETestBase):

    @patch("socialwarehouse.civic.services.nces_files.NCESFiles.load_edge_district_demographics")
    def test_writes_district_row_with_rate_computed(self, mock_loader):
        from socialwarehouse.civic.models import NCESDistrictEDGEDemographics

        mock_loader.return_value = pd.DataFrame([
            {"LEAID": "0600001", "STATEFP": "06",
             "TOT": 125_000, "CHILD_5_17": 22_500, "CHILD_LT5": 7_500,
             "WHITE_NH_5_17": 9_000, "BLACK_NH_5_17": 2_500,
             "ASIAN_NH_5_17": 1_200, "AIAN_NH_5_17": 150,
             "NHPI_NH_5_17": 90, "TWO_NH_5_17": 1_100,
             "HISPANIC_5_17": 8_460,
             "IPR_LT100_5_17": 3_375,  # ~15% poverty
             "HH_TOT": 45_000, "HH_WITH_CHILDREN": 12_000,
             "MEDIAN_HH_INC": 78_500,
             "ENGLISH_5_17": 17_000, "OTHER_LANG_5_17": 5_500,
             "FOREIGN_BORN_5_17": 1_200},
        ])

        call_command(
            "load_nces_edge",
            f"--vintage={self.vintage.name}",
            "--acs-endpoint=2018-22",
            "--state=06",
            verbosity=0,
        )

        d = NCESDistrictEDGEDemographics.objects.get(vintage=self.vintage, geoid="0600001")
        assert d.boundary_type == "school_district"
        assert d.state_fips == "06"
        assert d.source_acs_endpoint == "2018-22"
        assert d.total_population == 125_000
        assert d.population_5_17 == 22_500
        assert d.population_under_5 == 7_500
        assert d.pop_5_17_white_nh == 9_000
        assert d.pop_5_17_hispanic == 8_460
        assert d.pop_5_17_in_poverty == 3_375
        # 3375 / 22500 = 0.15
        assert d.pop_5_17_poverty_rate == Decimal("0.1500")
        assert d.median_household_income == 78_500


class TestLoadEDGENullsAndZeroDenom(LoadEDGETestBase):

    @patch("socialwarehouse.civic.services.nces_files.NCESFiles.load_edge_district_demographics")
    def test_poverty_rate_none_when_pop_zero(self, mock_loader):
        from socialwarehouse.civic.models import NCESDistrictEDGEDemographics

        mock_loader.return_value = pd.DataFrame([
            {"LEAID": "0600002", "STATEFP": "06",
             "TOT": 5_000, "CHILD_5_17": 0,
             "IPR_LT100_5_17": 0},
        ])

        call_command(
            "load_nces_edge", f"--vintage={self.vintage.name}",
            "--acs-endpoint=2018-22", "--state=06", verbosity=0,
        )

        d = NCESDistrictEDGEDemographics.objects.get(geoid="0600002")
        assert d.population_5_17 == 0
        assert d.pop_5_17_in_poverty == 0
        # Divide-by-zero → None, not exception.
        assert d.pop_5_17_poverty_rate is None

    @patch("socialwarehouse.civic.services.nces_files.NCESFiles.load_edge_district_demographics")
    def test_negative_sentinel_becomes_none(self, mock_loader):
        from socialwarehouse.civic.models import NCESDistrictEDGEDemographics

        mock_loader.return_value = pd.DataFrame([
            {"LEAID": "0600003", "STATEFP": "06",
             "TOT": -1, "CHILD_5_17": -9, "MEDIAN_HH_INC": -2},
        ])

        call_command(
            "load_nces_edge", f"--vintage={self.vintage.name}",
            "--acs-endpoint=2018-22", "--state=06", verbosity=0,
        )

        d = NCESDistrictEDGEDemographics.objects.get(geoid="0600003")
        assert d.total_population is None
        assert d.population_5_17 is None
        assert d.median_household_income is None


class TestLoadEDGEStateFilter(LoadEDGETestBase):

    @patch("socialwarehouse.civic.services.nces_files.NCESFiles.load_edge_district_demographics")
    def test_only_state_rows_written(self, mock_loader):
        from socialwarehouse.civic.models import NCESDistrictEDGEDemographics

        mock_loader.return_value = pd.DataFrame([
            {"LEAID": "0600001", "STATEFP": "06", "TOT": 1000, "CHILD_5_17": 100},
            {"LEAID": "4800001", "STATEFP": "48", "TOT": 2000, "CHILD_5_17": 200},
        ])

        call_command(
            "load_nces_edge", f"--vintage={self.vintage.name}",
            "--acs-endpoint=2018-22", "--state=06", verbosity=0,
        )

        rows = NCESDistrictEDGEDemographics.objects.filter(vintage=self.vintage)
        assert rows.count() == 1
        assert rows.first().geoid == "0600001"


class TestLoadEDGEValidation(LoadEDGETestBase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command(
                "load_nces_edge", "--vintage=NOT-A-VINTAGE",
                "--acs-endpoint=2018-22", "--state=06", verbosity=0,
            )
        assert "No NCESSchoolYearVintage" in str(cm.exception)


class TestLoadEDGEDryRun(LoadEDGETestBase):

    @patch("socialwarehouse.civic.services.nces_files.NCESFiles.load_edge_district_demographics")
    def test_dry_run_no_writes(self, mock_loader):
        from socialwarehouse.civic.models import NCESDistrictEDGEDemographics

        mock_loader.return_value = pd.DataFrame([
            {"LEAID": "0600001", "STATEFP": "06", "TOT": 1000},
        ])

        before = NCESDistrictEDGEDemographics.objects.count()
        call_command(
            "load_nces_edge", f"--vintage={self.vintage.name}",
            "--acs-endpoint=2018-22", "--state=06", "--dry-run",
            verbosity=0, stdout=StringIO(),
        )
        assert NCESDistrictEDGEDemographics.objects.count() == before
