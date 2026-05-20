"""Tests for E Phase 3 (SW#193): IRSSOI ingest + bucket model.

Mocks IRSSOIFiles.load so tests don't hit irs.gov. Pins:
- ZIP padding + 00000 / totals-row skip
- agi_stub == 0 totals skip
- bucket lookup via per-vintage IRSSOIIncomeBucket
- IRS column fallback (N2 / NUMDEP)
- idempotency, dry-run, unknown vintage
"""

from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class LoadIRSSOITestBase(TestCase):

    def setUp(self):
        from socialwarehouse.geo.models import IRSSOIVintage
        from datetime import date

        self.vintage = IRSSOIVintage.objects.filter(tax_year=2022).first()
        if self.vintage is None:
            self.vintage = IRSSOIVintage.objects.create(
                tax_year=2022,
                effective_from=date(2024, 12, 1),
            )
        # Seed buckets for this vintage.
        call_command(
            "seed_irs_soi_buckets", f"--vintage={self.vintage.name}",
            verbosity=0,
        )

    def _df(self, rows):
        return pd.DataFrame(rows)


class TestLoadIRSSOIHappyPath(LoadIRSSOITestBase):

    @patch("socialwarehouse.economic.services.irs_soi_files.IRSSOIFiles.load")
    def test_writes_aggregate_per_zcta_per_bucket(self, mock_load):
        from socialwarehouse.economic.models import (
            IRSSOIAggregate, IRSSOIIncomeBucket,
        )

        mock_load.return_value = self._df([
            {"zipcode": "94110", "agi_stub": 1, "N1": 1500, "N2": 2200,
             "A00100": 18_000_000, "A04800": 12_000_000, "A06500": 1_200_000},
            {"zipcode": "94110", "agi_stub": 6, "N1": 80, "N2": 110,
             "A00100": 65_000_000, "A04800": 55_000_000, "A06500": 16_000_000},
            {"zipcode": "00000", "agi_stub": 0, "N1": 99999},  # state total — skip
        ])

        call_command(
            "load_irs_soi", f"--vintage={self.vintage.name}",
            "--state-abbrev=CA", verbosity=0,
        )

        rows = IRSSOIAggregate.objects.filter(vintage=self.vintage)
        assert rows.count() == 2

        b1 = IRSSOIIncomeBucket.objects.get(vintage=self.vintage, bucket_code=1)
        low = rows.get(geoid="94110", agi_bin=b1)
        assert low.return_count == 1500
        assert low.agi_total == 18_000_000

        b6 = IRSSOIIncomeBucket.objects.get(vintage=self.vintage, bucket_code=6)
        high = rows.get(geoid="94110", agi_bin=b6)
        assert high.total_tax_total == 16_000_000


class TestLoadIRSSOIColumnFallback(LoadIRSSOITestBase):

    @patch("socialwarehouse.economic.services.irs_soi_files.IRSSOIFiles.load")
    def test_numdep_used_when_n2_absent(self, mock_load):
        from socialwarehouse.economic.models import IRSSOIAggregate

        mock_load.return_value = self._df([
            {"zipcode": "94110", "agi_stub": 1, "N1": 1500, "NUMDEP": 1800,
             "A00100": 1, "A04800": 1, "A06500": 1},
        ])

        call_command(
            "load_irs_soi", f"--vintage={self.vintage.name}",
            "--state-abbrev=CA", verbosity=0,
        )

        row = IRSSOIAggregate.objects.get(vintage=self.vintage, geoid="94110")
        assert row.exemption_count == 1800


class TestLoadIRSSOIIdempotent(LoadIRSSOITestBase):

    @patch("socialwarehouse.economic.services.irs_soi_files.IRSSOIFiles.load")
    def test_rerun_overwrites(self, mock_load):
        from socialwarehouse.economic.models import IRSSOIAggregate

        mock_load.return_value = self._df([
            {"zipcode": "94110", "agi_stub": 1, "N1": 100,
             "A00100": 1, "A04800": 1, "A06500": 1},
        ])
        call_command("load_irs_soi", f"--vintage={self.vintage.name}",
                     "--state-abbrev=CA", verbosity=0)

        mock_load.return_value = self._df([
            {"zipcode": "94110", "agi_stub": 1, "N1": 1500,
             "A00100": 1, "A04800": 1, "A06500": 1},
        ])
        call_command("load_irs_soi", f"--vintage={self.vintage.name}",
                     "--state-abbrev=CA", verbosity=0)

        rows = IRSSOIAggregate.objects.filter(geoid="94110")
        assert rows.count() == 1
        assert rows.first().return_count == 1500


class TestLoadIRSSOIValidation(TestCase):

    def test_unknown_vintage_raises(self):
        with self.assertRaises(CommandError) as cm:
            call_command("load_irs_soi", "--vintage=TY9999",
                         "--state-abbrev=CA", verbosity=0)
        assert "No IRSSOIVintage" in str(cm.exception)

    def test_missing_buckets_raises(self):
        """If no IRSSOIIncomeBucket rows are seeded for the vintage,
        the load command refuses to run rather than silently dropping
        everything."""
        from socialwarehouse.geo.models import IRSSOIVintage
        from datetime import date

        bare = IRSSOIVintage.objects.create(
            tax_year=2099,
            effective_from=date(2099, 1, 1),
        )
        with self.assertRaises(CommandError) as cm:
            call_command("load_irs_soi", f"--vintage={bare.name}",
                         "--state-abbrev=CA", verbosity=0)
        assert "IRSSOIIncomeBucket" in str(cm.exception)


class TestLoadIRSSOIDryRun(LoadIRSSOITestBase):

    @patch("socialwarehouse.economic.services.irs_soi_files.IRSSOIFiles.load")
    def test_dry_run_no_writes(self, mock_load):
        from socialwarehouse.economic.models import IRSSOIAggregate

        mock_load.return_value = self._df([
            {"zipcode": "94110", "agi_stub": 1, "N1": 1,
             "A00100": 1, "A04800": 1, "A06500": 1},
        ])

        before = IRSSOIAggregate.objects.count()
        call_command("load_irs_soi", f"--vintage={self.vintage.name}",
                     "--state-abbrev=CA", "--dry-run",
                     verbosity=0, stdout=StringIO())
        assert IRSSOIAggregate.objects.count() == before


class TestSeedIRSSOIBuckets(TestCase):

    def test_creates_six_buckets(self):
        from socialwarehouse.economic.models import IRSSOIIncomeBucket
        from socialwarehouse.geo.models import IRSSOIVintage
        from datetime import date

        v = IRSSOIVintage.objects.create(
            tax_year=2021,
            effective_from=date(2023, 12, 1),
        )
        call_command("seed_irs_soi_buckets", f"--vintage={v.name}", verbosity=0)
        assert IRSSOIIncomeBucket.objects.filter(vintage=v).count() == 6
        # Re-run is idempotent.
        call_command("seed_irs_soi_buckets", f"--vintage={v.name}", verbosity=0)
        assert IRSSOIIncomeBucket.objects.filter(vintage=v).count() == 6
