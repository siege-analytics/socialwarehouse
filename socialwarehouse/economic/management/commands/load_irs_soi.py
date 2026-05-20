"""Load IRS SOI ZIP-code aggregates into IRSSOIAggregate.

Per E Phase 3. Files-only (no API key). Bucket model is per-vintage
(see seed_irs_soi_buckets). Idempotent via update_or_create on
(vintage, boundary_type='zcta', geoid, agi_bin).

Usage:
    python manage.py load_irs_soi --vintage TY2022 --state-abbrev CA
    python manage.py load_irs_soi --vintage TY2022 --state-abbrev CA --dry-run
"""

import logging
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


logger = logging.getLogger(__name__)


# IRS SOI columns we ingest. Map: model field -> IRS column candidates
# (tuple; first non-null wins, handles year-over-year header drift).
FIELD_MAP = {
    "return_count":         ("N1",),
    "exemption_count":      ("N2", "NUMDEP"),
    "agi_total":            ("A00100",),
    "taxable_income_total": ("A04800",),
    "total_tax_total":      ("A06500",),
}


class Command(BaseCommand):
    help = "Load IRS SOI per-ZCTA aggregates via the files-only helper."

    def add_arguments(self, parser):
        parser.add_argument("--vintage", type=str, required=True,
            help="IRSSOIVintage name, e.g. 'TY2022'.")
        parser.add_argument("--state-abbrev", type=str, required=True,
            help="2-letter state abbreviation (e.g., 'CA').")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from socialwarehouse.economic.models import (
            IRSSOIAggregate, IRSSOIIncomeBucket,
        )
        from socialwarehouse.economic.services.irs_soi_files import IRSSOIFiles
        from socialwarehouse.geo.models import IRSSOIVintage

        vintage_name = options["vintage"]
        state_abbrev = options["state_abbrev"]
        dry_run = options["dry_run"]

        try:
            vintage = IRSSOIVintage.objects.get(name=vintage_name)
        except IRSSOIVintage.DoesNotExist:
            raise CommandError(
                f"No IRSSOIVintage with name={vintage_name!r}."
            )

        bucket_lookup = {
            b.bucket_code: b for b in
            IRSSOIIncomeBucket.objects.filter(vintage=vintage)
        }
        if not bucket_lookup:
            raise CommandError(
                f"No IRSSOIIncomeBucket rows for vintage={vintage.name}. "
                "Run `seed_irs_soi_buckets --vintage=...` first."
            )

        self.stdout.write(
            f"SOI vintage={vintage.name} tax_year={vintage.tax_year} "
            f"state={state_abbrev}"
        )

        files = IRSSOIFiles()
        df = files.load(tax_year=vintage.tax_year, state_abbrev=state_abbrev)
        if df.empty:
            self.stdout.write(self.style.WARNING("IRS parse returned no rows."))
            return

        self.stdout.write(f"Parsed {len(df)} SOI rows; writing to IRSSOIAggregate...")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write up to {len(df)} IRSSOIAggregate rows."
            ))
            return

        written = 0
        skipped_total = 0
        with transaction.atomic():
            for _, row in df.iterrows():
                zipcode = self._zip(row)
                if not zipcode:
                    continue
                bucket_code = self._int(row.get("agi_stub"))
                # bucket_code 0 = totals row (across all buckets); skip,
                # the warehouse holds per-bucket only.
                if bucket_code in (0, None):
                    skipped_total += 1
                    continue
                bucket = bucket_lookup.get(bucket_code)
                if bucket is None:
                    continue

                defaults = {}
                for model_field, candidates in FIELD_MAP.items():
                    defaults[model_field] = self._first_int(row, candidates)

                IRSSOIAggregate.objects.update_or_create(
                    vintage=vintage,
                    boundary_type="zcta",
                    geoid=zipcode,
                    agi_bin=bucket,
                    defaults=defaults,
                )
                written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} IRSSOIAggregate rows for {vintage.name} "
            f"state={state_abbrev}. Skipped {skipped_total} totals rows."
        ))

    # ------------------------------------------------------------------
    @staticmethod
    def _zip(row):
        raw = row.get("zipcode") or row.get("ZIPCODE") or row.get("zip_code")
        if raw is None:
            return ""
        s = str(int(raw)) if not isinstance(raw, str) else raw.strip()
        # IRS files sometimes use "00000" for state-rollup. Skip.
        if not s or s == "00000":
            return ""
        return s.zfill(5)

    @staticmethod
    def _int(raw):
        if raw is None:
            return None
        try:
            if raw.__class__.__name__ == "float" and raw != raw:
                return None
        except Exception:
            pass
        try:
            return int(Decimal(str(raw)))
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def _first_int(cls, row, candidates):
        for col in candidates:
            v = cls._int(row.get(col))
            if v is not None:
                return v
        return None
