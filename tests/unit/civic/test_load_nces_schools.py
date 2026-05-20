"""Tests for F Phase 1b: NCESSchoolAggregate + load_nces_schools.

Mocks NCESFiles's school-level loaders. Pins:
- School type / status code mapping.
- Charter / magnet / title-I boolean parsing from NCES Yes/No strings.
- Negative-sentinel coercion.
- State filter.
"""

from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadNCESSchoolsTestBase(TestCase):

    def setUp(self):
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        self.vintage = NCESSchoolYearVintage.objects.filter(start_year=2022, end_year=2023).first()
        if self.vintage is None:
            self.vintage = NCESSchoolYearVintage.objects.create(
                start_year=2022, end_year=2023,
                effective_from=date(2022, 8, 1), effective_to=date(2023, 8, 1),
            )

    def _patch_loaders(self, directory_rows, nonfiscal_rows):
        return patch.multiple(
            "socialwarehouse.civic.services.nces_files.NCESFiles",
            load_ccd_school_directory=lambda self, school_year: pd.DataFrame(directory_rows),
            load_ccd_school_nonfiscal=lambda self, school_year: pd.DataFrame(nonfiscal_rows),
        )


class TestLoadSchoolsHappyPath(LoadNCESSchoolsTestBase):

    def test_writes_school_with_joined_nonfiscal(self):
        from socialwarehouse.civic.models import NCESSchoolAggregate

        directory = [
            {"NCESSCH": "060000100001", "LEAID": "0600001", "STATEFIPS": "06",
             "SCH_NAME": "Lincoln High", "SCH_TYPE": "1", "SY_STATUS": "1",
             "CHARTER_TEXT": "No", "MAGNET_TEXT": "Yes", "TITLEI_STATUS": "1",
             "GSLO": "09", "GSHI": "12"},
        ]
        nonfiscal = [
            {"NCESSCH": "060000100001", "TOTAL": 2100, "FTE": 115.0,
             "G09": 540, "G10": 525, "G11": 520, "G12": 515,
             "TOTFRL": 850, "PK": 0, "KG": 0},
        ]

        with self._patch_loaders(directory, nonfiscal):
            call_command("load_nces_schools", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        s = NCESSchoolAggregate.objects.get(vintage=self.vintage, geoid="060000100001")
        assert s.school_name == "Lincoln High"
        assert s.school_type == "regular"
        assert s.school_status == "open"
        assert s.is_charter is False
        assert s.is_magnet is True
        assert s.is_title_i is True
        assert s.grade_low == "09"
        assert s.grade_high == "12"
        assert s.enrollment_total == 2100
        assert s.enrollment_grade_9_12 == 2100  # sum of G09..G12
        assert s.teachers_fte == Decimal("115.00")
        assert s.leaid == "0600001"


class TestLoadSchoolsNegativeSentinels(LoadNCESSchoolsTestBase):

    def test_negative_values_become_null(self):
        from socialwarehouse.civic.models import NCESSchoolAggregate

        directory = [
            {"NCESSCH": "060000100002", "LEAID": "0600001", "STATEFIPS": "06",
             "SCH_NAME": "Test School", "SCH_TYPE": "1", "SY_STATUS": "1"},
        ]
        nonfiscal = [
            {"NCESSCH": "060000100002", "TOTAL": -1, "FTE": -2, "TOTFRL": 100},
        ]

        with self._patch_loaders(directory, nonfiscal):
            call_command("load_nces_schools", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        s = NCESSchoolAggregate.objects.get(vintage=self.vintage, geoid="060000100002")
        assert s.enrollment_total is None
        assert s.teachers_fte is None
        assert s.free_lunch_eligible_count == 100


class TestLoadSchoolsStateFilter(LoadNCESSchoolsTestBase):

    def test_only_state_rows_written(self):
        from socialwarehouse.civic.models import NCESSchoolAggregate

        directory = [
            {"NCESSCH": "060000100001", "LEAID": "0600001", "STATEFIPS": "06",
             "SCH_NAME": "CA School", "SCH_TYPE": "1", "SY_STATUS": "1"},
            {"NCESSCH": "480000100001", "LEAID": "4800001", "STATEFIPS": "48",
             "SCH_NAME": "TX School", "SCH_TYPE": "1", "SY_STATUS": "1"},
        ]
        nonfiscal = [
            {"NCESSCH": "060000100001", "TOTAL": 1500, "FTE": 80},
            {"NCESSCH": "480000100001", "TOTAL": 2000, "FTE": 100},
        ]

        with self._patch_loaders(directory, nonfiscal):
            call_command("load_nces_schools", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        rows = NCESSchoolAggregate.objects.filter(vintage=self.vintage)
        assert rows.count() == 1
        assert rows.first().geoid == "060000100001"


class TestLoadSchoolsCharter(LoadNCESSchoolsTestBase):

    def test_charter_yes(self):
        from socialwarehouse.civic.models import NCESSchoolAggregate

        directory = [
            {"NCESSCH": "060000100003", "LEAID": "0600001", "STATEFIPS": "06",
             "SCH_NAME": "Charter Academy", "SCH_TYPE": "1", "SY_STATUS": "1",
             "CHARTER_TEXT": "Yes"},
        ]
        with self._patch_loaders(directory, []):
            call_command("load_nces_schools", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)
        assert NCESSchoolAggregate.objects.get(geoid="060000100003").is_charter is True


class TestLoadSchoolsValidation(LoadNCESSchoolsTestBase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command("load_nces_schools", "--vintage=NOT-A-VINTAGE", "--state=06", verbosity=0)
        assert "No NCESSchoolYearVintage" in str(cm.exception)


class TestLoadSchoolsDryRun(LoadNCESSchoolsTestBase):

    def test_dry_run_no_writes(self):
        from socialwarehouse.civic.models import NCESSchoolAggregate

        directory = [
            {"NCESSCH": "060000100001", "LEAID": "0600001", "STATEFIPS": "06",
             "SCH_NAME": "X", "SCH_TYPE": "1", "SY_STATUS": "1"},
        ]
        before = NCESSchoolAggregate.objects.count()
        with self._patch_loaders(directory, []):
            call_command("load_nces_schools", f"--vintage={self.vintage.name}", "--state=06",
                         "--dry-run", verbosity=0, stdout=StringIO())
        assert NCESSchoolAggregate.objects.count() == before
