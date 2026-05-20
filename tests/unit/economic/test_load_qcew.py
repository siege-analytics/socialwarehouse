"""Tests for E Phase 1 (SW#193): BLSQCEWAggregate model + load_qcew.

Mocks the QCEWFiles helper so tests don't hit BLS. Pins the
ingest contract: county-level rows, NAICS filter, ownership-code
mapping, update_or_create idempotency.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadQCEWTestBase(TestCase):

    def setUp(self):
        from socialwarehouse.geo.models import BLSQCEWVintage

        self.vintage = BLSQCEWVintage.objects.filter(year=2024, quarter=3).first()
        if self.vintage is None:
            # CI seed may not include 2024Q3 yet; create one.
            from datetime import date
            self.vintage = BLSQCEWVintage.objects.create(
                year=2024, quarter=3,
                effective_from=date(2024, 7, 1),
                effective_to=date(2024, 10, 1),
            )

    def _df(self, rows):
        return pd.DataFrame(rows)


class TestLoadQCEWHappyPath(LoadQCEWTestBase):

    @patch("socialwarehouse.economic.services.bls_qcew_files.QCEWFiles.load")
    def test_writes_county_aggregates(self, mock_load):
        from socialwarehouse.economic.models import BLSQCEWAggregate

        mock_load.return_value = self._df([
            {"area_fips": "06037", "own_code": "5", "industry_code": "10",  # county, private, all-industries total
             "qtrly_estabs": 230_000, "month3_emplvl": 4_125_000,
             "total_qtrly_wages": 87_500_000_000, "avg_wkly_wage": 1_650, "qtr": 3, "year": 2024},
            {"area_fips": "06037", "own_code": "5", "industry_code": "23",  # construction sector
             "qtrly_estabs": 18_500, "month3_emplvl": 152_000,
             "total_qtrly_wages": 2_800_000_000, "avg_wkly_wage": 1_420, "qtr": 3, "year": 2024},
            {"area_fips": "06037", "own_code": "0", "industry_code": "10",  # total covered, all-industries
             "qtrly_estabs": 240_000, "month3_emplvl": 4_400_000,
             "total_qtrly_wages": 90_000_000_000, "avg_wkly_wage": 1_700, "qtr": 3, "year": 2024},
        ])

        call_command(
            "load_qcew", f"--vintage={self.vintage.name}", "--state=06",
            verbosity=0,
        )

        rows = BLSQCEWAggregate.objects.filter(vintage=self.vintage, boundary_type="county", geoid="06037")
        assert rows.count() == 3

        private_total = rows.get(ownership_code="5", industry_code="10")
        assert private_total.avg_monthly_employment == 4_125_000
        assert private_total.total_quarterly_wages == 87_500_000_000
        assert private_total.avg_weekly_wage == 1_650
        assert private_total.establishment_count == 230_000

        construction = rows.get(ownership_code="5", industry_code="23")
        assert construction.industry_code == "23"


class TestLoadQCEWFiltersNonCountyRows(LoadQCEWTestBase):

    @patch("socialwarehouse.economic.services.bls_qcew_files.QCEWFiles.load")
    def test_state_rows_skipped_in_phase1(self, mock_load):
        from socialwarehouse.economic.models import BLSQCEWAggregate

        mock_load.return_value = self._df([
            {"area_fips": "06", "own_code": "5", "industry_code": "10",  # STATE-level row
             "qtrly_estabs": 0, "month3_emplvl": 0, "total_qtrly_wages": 0, "avg_wkly_wage": 0,
             "qtr": 3, "year": 2024},
            {"area_fips": "06037", "own_code": "5", "industry_code": "10",
             "qtrly_estabs": 1, "month3_emplvl": 100, "total_qtrly_wages": 1000, "avg_wkly_wage": 250,
             "qtr": 3, "year": 2024},
        ])

        call_command("load_qcew", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        rows = BLSQCEWAggregate.objects.filter(vintage=self.vintage)
        # Only the county-shape (5-digit) row writes.
        assert rows.count() == 1
        assert rows.first().geoid == "06037"


class TestLoadQCEWIdempotent(LoadQCEWTestBase):

    @patch("socialwarehouse.economic.services.bls_qcew_files.QCEWFiles.load")
    def test_rerun_overwrites(self, mock_load):
        from socialwarehouse.economic.models import BLSQCEWAggregate

        mock_load.return_value = self._df([
            {"area_fips": "06037", "own_code": "5", "industry_code": "10",
             "qtrly_estabs": 100, "month3_emplvl": 4_000_000,
             "total_qtrly_wages": 85_000_000_000, "avg_wkly_wage": 1_600,
             "qtr": 3, "year": 2024},
        ])
        call_command("load_qcew", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        mock_load.return_value = self._df([
            {"area_fips": "06037", "own_code": "5", "industry_code": "10",
             "qtrly_estabs": 230_000, "month3_emplvl": 4_125_000,
             "total_qtrly_wages": 87_500_000_000, "avg_wkly_wage": 1_650,
             "qtr": 3, "year": 2024},
        ])
        call_command("load_qcew", f"--vintage={self.vintage.name}", "--state=06", verbosity=0)

        rows = BLSQCEWAggregate.objects.filter(geoid="06037", industry_code="10", ownership_code="5")
        assert rows.count() == 1
        assert rows.first().establishment_count == 230_000


class TestLoadQCEWValidation(LoadQCEWTestBase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command(
                "load_qcew", "--vintage=NOT-A-VINTAGE", "--state=06",
                verbosity=0,
            )
        assert "No BLSQCEWVintage" in str(cm.exception)


class TestLoadQCEWDryRun(LoadQCEWTestBase):

    @patch("socialwarehouse.economic.services.bls_qcew_files.QCEWFiles.load")
    def test_dry_run_no_writes(self, mock_load):
        from socialwarehouse.economic.models import BLSQCEWAggregate

        mock_load.return_value = self._df([
            {"area_fips": "06037", "own_code": "5", "industry_code": "10",
             "qtrly_estabs": 1, "month3_emplvl": 1, "total_qtrly_wages": 1, "avg_wkly_wage": 1,
             "qtr": 3, "year": 2024},
        ])

        before = BLSQCEWAggregate.objects.count()
        call_command("load_qcew", f"--vintage={self.vintage.name}", "--state=06",
                     "--dry-run", verbosity=0, stdout=StringIO())
        assert BLSQCEWAggregate.objects.count() == before
