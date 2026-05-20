"""Load BLS QCEW employment + wages aggregates into the warehouse.

Per E Q1 = (a) 2-digit NAICS (sector-level) for Phase 1.
Per E Q4 = (a) files-only path (no BLS API key needed).

Phase 1 ingests county-level data (own_code='5' Private + own_code='0'
Total Covered, NAICS at the configured depth, default 2). CBSA-level
ingest is Phase 2 once C ships the `cbsa` boundary type.

Usage:
    python manage.py load_qcew --vintage 2024Q3 --state 06
    python manage.py load_qcew --vintage 2024Q3 --state 06 --naics-depth 3
    python manage.py load_qcew --vintage 2024Q3 --state 06 --dry-run

Uses socialwarehouse.economic.services.bls_qcew_files.QCEWFiles for
the download/parse — SU#533 tracks lifting that helper to SU.
"""

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Load BLS QCEW aggregates from open-data files into the warehouse."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vintage", type=str, required=True,
            help="Vintage name like '2024Q3'. Must match a BLSQCEWVintage row.",
        )
        parser.add_argument(
            "--state", type=str, required=True,
            help="2-digit state FIPS code; restricts the parse to this state.",
        )
        parser.add_argument(
            "--naics-depth", type=int, default=2,
            help="NAICS code length; 2 = sector (default), 3 = subsector, etc.",
        )
        parser.add_argument(
            "--boundary-type", type=str, default="county",
            choices=["county", "cbsa", "both"],
            help=(
                "Which BLS aggregation levels to load. 'county' (default) keeps "
                "Phase 1's county-only behavior. 'cbsa' loads MSA-level rows. "
                "'both' loads county + MSA in one pass."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch + report counts without writing.",
        )

    def handle(self, *args, **options):
        from socialwarehouse.economic.models import BLSQCEWAggregate
        from socialwarehouse.economic.services.bls_qcew_files import QCEWFiles
        from socialwarehouse.geo.models import BLSQCEWVintage

        vintage_name = options["vintage"]
        state_fips = options["state"]
        naics_depth = options["naics_depth"]
        boundary_type_arg = options["boundary_type"]
        dry_run = options["dry_run"]

        # Resolve vintage.
        try:
            vintage = BLSQCEWVintage.objects.get(name=vintage_name)
        except BLSQCEWVintage.DoesNotExist:
            raise CommandError(
                f"No BLSQCEWVintage with name={vintage_name!r}. "
                f"Available examples: "
                f"{list(BLSQCEWVintage.objects.values_list('name', flat=True)[:5])}…"
            )

        self.stdout.write(
            f"QCEW vintage={vintage.name} year={vintage.year} quarter={vintage.quarter} "
            f"state={state_fips} naics_depth={naics_depth}"
        )

        files = QCEWFiles()
        df = files.load(
            year=vintage.year, quarter=vintage.quarter,
            state_fips=state_fips, naics_depth=naics_depth,
        )

        if df.empty:
            self.stdout.write(self.style.WARNING("QCEW parse returned no rows."))
            return

        self.stdout.write(f"Parsed {len(df)} QCEW rows; writing to BLSQCEWAggregate...")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write {len(df)} BLSQCEWAggregate rows."
            ))
            return

        written = 0
        with transaction.atomic():
            for _, row in df.iterrows():
                area_fips = str(row["area_fips"])
                boundary_type, geoid = self._classify_row(area_fips, row.get("agglvl_code"))
                if boundary_type is None:
                    continue
                if boundary_type_arg != "both" and boundary_type != boundary_type_arg:
                    continue

                BLSQCEWAggregate.objects.update_or_create(
                    vintage=vintage,
                    boundary_type=boundary_type,
                    geoid=geoid,
                    ownership_code=str(row["own_code"]),
                    industry_code=str(row["industry_code"]),
                    defaults={
                        "avg_monthly_employment": self._to_int(row.get("month3_emplvl")),
                        "total_quarterly_wages": self._to_int(row.get("total_qtrly_wages")),
                        "avg_weekly_wage": self._to_int(row.get("avg_wkly_wage")),
                        "establishment_count": self._to_int(row.get("qtrly_estabs")),
                    },
                )
                written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} BLSQCEWAggregate rows for {vintage.name} state={state_fips}."
        ))

    @staticmethod
    def _classify_row(area_fips, agglvl_code):
        """Classify a QCEW row's boundary_type + geoid.

        BLS convention:
          - County area_fips: 5 digits, purely numeric (e.g. "06037").
            agglvl_code starts with '5'.
          - MSA / CBSA area_fips: "C" prefix + 4 digits (e.g. "C3108"
            for CBSA 31084 — BLS drops the leading digit). agglvl_code
            starts with '4'.
          - National / state / other aggregates: skipped.

        Returns (boundary_type, geoid) or (None, None) to skip.
        For CBSA rows, the returned geoid is the area_fips as-published
        ("C3108" etc.) — analysts who want to join against Census CBSA
        codes can either translate at query time or wait for a future
        normalization pass.
        """
        if not area_fips:
            return None, None
        agglvl = str(agglvl_code or "")
        if agglvl.startswith("5") and len(area_fips) == 5 and area_fips.isdigit():
            return "county", area_fips
        if agglvl.startswith("4") and area_fips.startswith("C"):
            return "cbsa", area_fips
        # National (agglvl 1x), state (agglvl 2x/3x), or unknown — skip.
        return None, None

    @staticmethod
    def _to_int(raw):
        if raw is None:
            return None
        try:
            # Pandas may give floats from CSVs.
            return int(Decimal(str(raw)))
        except Exception:
            return None
