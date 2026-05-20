"""Tests for F Phase 1a (SW#194): NCESDistrictAggregate + load_nces.

Mocks NCESFiles so tests don't hit nces.ed.gov. Pins the
directory + nonfiscal + finance row-joining logic and the
NCES negative-sentinel handling.
"""

from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadNCESTestBase(TestCase):

    def setUp(self):
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        self.vintage = NCESSchoolYearVintage.objects.filter(start_year=2022, end_year=2023).first()
        if self.vintage is None:
            self.vintage = NCESSchoolYearVintage.objects.create(
                start_year=2022, end_year=2023,
                effective_from=date(2022, 8, 1), effective_to=date(2023, 8, 1),
            )

    def _patch_loaders(self, directory_rows, nonfiscal_rows, finance_rows):
        """Yield a context that patches NCESFiles's three load methods."""
        return patch.multiple(
            "socialwarehouse.civic.services.nces_files.NCESFiles",
            load_ccd_directory=lambda self, school_year: pd.DataFrame(directory_rows),
            load_ccd_nonfiscal=lambda self, school_year: pd.DataFrame(nonfiscal_rows),
            load_ccd_finance=lambda self, school_year: pd.DataFrame(finance_rows),
        )


class TestLoadNCESHappyPath(LoadNCESTestBase):

    def test_writes_district_aggregate_with_joined_rows(self):
        from socialwarehouse.civic.models import NCESDistrictAggregate

        directory = [
            {"LEAID": "0600001", "STATEFIPS": "06", "AGCHRT": "1", "LEA_NAME": "Test District"},
        ]
        nonfiscal = [
            {"LEAID": "0600001", "TOTAL": 4200, "TOTTCH": 215.5,
             "TOTFRL": 1100, "G09": 1100, "G10": 1050, "G11": 1025, "G12": 1025,
             "PK": 50, "KG": 350, "G01": 320, "G02": 318, "G03": 322, "G04": 319, "G05": 321,
             "G06": 320, "G07": 319, "G08": 321},
        ]
        finance = [
            {"LEAID": "0600001",
             "TOTALREV": 55_000_000, "TFEDREV": 3_200_000, "C14": 1_500_000, "C15": 700_000,
             "TSTREV": 32_000_000, "STR": 28_000_000,
             "TLOCREV": 19_800_000, "T06": 14_500_000,
             "TOTALEXP": 54_500_000, "TCURINST": 28_000_000, "TCURSSVC": 12_000_000,
             "TCAPOUT": 5_500_000, "PPCSTOT": 12_976},
        ]

        with self._patch_loaders(directory, nonfiscal, finance):
            call_command("load_nces", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        agg = NCESDistrictAggregate.objects.get(vintage=self.vintage, geoid="0600001")
        assert agg.boundary_type == "school_district"
        assert agg.state_fips == "06"
        assert agg.district_type == "unified"
        assert agg.enrollment_total == 4200
        assert agg.teachers_fte == Decimal("215.50")
        # PK+KG = 50+350 = 400
        assert agg.enrollment_pk_grade_k == 400
        # G09..G12 = 1100+1050+1025+1025 = 4200
        assert agg.enrollment_grade_9_12 == 4200
        assert agg.revenue_total == 55_000_000
        assert agg.revenue_federal_title_i == 1_500_000
        assert agg.expenditure_per_pupil == 12_976


class TestLoadNCESNegativeSentinels(LoadNCESTestBase):

    def test_negative_sentinel_becomes_null(self):
        """NCES uses -1, -2, -3, -9 to mean missing/suppressed; coerce to None."""
        from socialwarehouse.civic.models import NCESDistrictAggregate

        directory = [{"LEAID": "0600002", "STATEFIPS": "06", "AGCHRT": "1"}]
        nonfiscal = [{"LEAID": "0600002", "TOTAL": -1, "TOTTCH": -2, "TOTFRL": 800}]
        finance = [{"LEAID": "0600002", "TOTALREV": -9, "TFEDREV": 1_000_000}]

        with self._patch_loaders(directory, nonfiscal, finance):
            call_command("load_nces", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        agg = NCESDistrictAggregate.objects.get(vintage=self.vintage, geoid="0600002")
        assert agg.enrollment_total is None
        assert agg.teachers_fte is None
        assert agg.free_lunch_eligible_count == 800
        assert agg.revenue_total is None
        assert agg.revenue_federal == 1_000_000


class TestLoadNCESStateFilter(LoadNCESTestBase):

    def test_only_state_rows_written(self):
        from socialwarehouse.civic.models import NCESDistrictAggregate

        directory = [
            {"LEAID": "0600001", "STATEFIPS": "06", "AGCHRT": "1"},
            {"LEAID": "4800001", "STATEFIPS": "48", "AGCHRT": "1"},  # Texas
        ]
        nonfiscal = [
            {"LEAID": "0600001", "TOTAL": 4200, "TOTTCH": 200},
            {"LEAID": "4800001", "TOTAL": 50_000, "TOTTCH": 2_500},
        ]
        finance = []

        with self._patch_loaders(directory, nonfiscal, finance):
            call_command("load_nces", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        rows = NCESDistrictAggregate.objects.filter(vintage=self.vintage)
        assert rows.count() == 1
        assert rows.first().geoid == "0600001"


class TestLoadNCESValidation(LoadNCESTestBase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command("load_nces", "--vintage=NOT-A-VINTAGE", "--state=06", verbosity=0)
        assert "No NCESSchoolYearVintage" in str(cm.exception)


class TestLoadNCESDryRun(LoadNCESTestBase):

    def test_dry_run_no_writes(self):
        from socialwarehouse.civic.models import NCESDistrictAggregate

        directory = [{"LEAID": "0600001", "STATEFIPS": "06", "AGCHRT": "1"}]
        nonfiscal = [{"LEAID": "0600001", "TOTAL": 1000}]
        finance = []

        before = NCESDistrictAggregate.objects.count()
        with self._patch_loaders(directory, nonfiscal, finance):
            call_command("load_nces", f"--vintage={self.vintage.name}", "--state=06",
                         "--dry-run", verbosity=0, stdout=StringIO())
        assert NCESDistrictAggregate.objects.count() == before


class TestParseSchoolYear(TestCase):
    """Quick sanity test for NCESFiles._parse_school_year."""

    def test_basic_parse(self):
        from socialwarehouse.civic.services.nces_files import NCESFiles

        assert NCESFiles._parse_school_year("2022-23") == (2022, 2023)
        assert NCESFiles._parse_school_year("2009-10") == (2009, 2010)
        assert NCESFiles._parse_school_year("2099-00") == (2099, 2100)

    def test_invalid_format_raises(self):
        from socialwarehouse.civic.services.nces_files import NCESFiles

        with self.assertRaises(ValueError):
            NCESFiles._parse_school_year("2022")
