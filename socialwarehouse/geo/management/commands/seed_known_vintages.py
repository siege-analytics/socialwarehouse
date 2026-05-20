"""Pre-populate Vintage rows for every known vintage across the four
data domains.

Template-readiness B (SW#190 PR #1, additive): seeds the Vintage table
with the published-vintage catalogs each domain ships with. Idempotent
— rerunning adds only new vintages, never duplicates.

Usage:
    python manage.py seed_known_vintages
    python manage.py seed_known_vintages --kinds census-decadal,acs
    python manage.py seed_known_vintages --dry-run

Run automatically by the migration that creates the Vintage tables; can
also be invoked manually after new vintages are published upstream
(e.g., after Census drops 2030 boundaries, or after BLS publishes
2025Q1 QCEW).

Per the v2 design: redistricting-plan vintages are NOT pre-seeded by
this command. Those rows are created on demand from
siege_utilities.RedistrictingPlan as `assign_boundaries` writes ABP
rows for new plans.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction


# Cutoffs / catalogs per kind. Update as new vintages are published.

CENSUS_DECADES = [2010, 2020]  # add 2030 when boundaries drop

ACS_5YEAR_ENDPOINTS = list(range(2013, 2024))  # 2009-2013 through 2019-2023
ACS_1YEAR_YEARS = [y for y in range(2010, 2024) if y != 2020]  # ACS 1-year skipped 2020 (COVID)

BLS_QCEW_RANGE = [
    (year, quarter) for year in range(2010, 2025) for quarter in range(1, 5)
]  # 2010Q1 through 2024Q4

BEA_REGIONAL_YEARS = list(range(2010, 2025))  # 2010 through 2024

NCES_SCHOOL_YEARS = [(start, start + 1) for start in range(2010, 2024)]  # 2010-11 through 2023-24


ALL_KINDS = ["census-decadal", "acs", "bls-qcew", "bea-regional", "nces-school-year"]


class Command(BaseCommand):
    help = "Pre-populate Vintage rows for known published vintages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kinds",
            type=str,
            default=",".join(ALL_KINDS),
            help=(
                f"Comma-separated kinds to seed. Default: all five "
                f"({', '.join(ALL_KINDS)}). 'redistricting-plan' is "
                f"created on demand by assign_boundaries and is NOT "
                f"seeded by this command."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing.",
        )

    def handle(self, *args, **options):
        kinds = set(options["kinds"].split(","))
        dry_run = options["dry_run"]
        unknown = kinds - set(ALL_KINDS)
        if unknown:
            self.stdout.write(self.style.ERROR(
                f"Unknown kinds: {', '.join(sorted(unknown))}. "
                f"Valid: {', '.join(ALL_KINDS)}"
            ))
            return

        created_total = 0
        with transaction.atomic():
            if "census-decadal" in kinds:
                created_total += self._seed_census_decadal(dry_run)
            if "acs" in kinds:
                created_total += self._seed_acs(dry_run)
            if "bls-qcew" in kinds:
                created_total += self._seed_bls_qcew(dry_run)
            if "bea-regional" in kinds:
                created_total += self._seed_bea_regional(dry_run)
            if "nces-school-year" in kinds:
                created_total += self._seed_nces_school_year(dry_run)
            if dry_run:
                transaction.set_rollback(True)

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created_total} vintage rows."))

    def _seed_census_decadal(self, dry_run):
        from socialwarehouse.geo.models import CensusDecadalVintage

        created = 0
        latest_decade = max(CENSUS_DECADES)
        for decade in CENSUS_DECADES:
            if CensusDecadalVintage.objects.filter(decade=decade).exists():
                continue
            eff_from = date(decade, 1, 1)
            eff_to = None if decade == latest_decade else date(decade + 10, 1, 1)
            if dry_run:
                self.stdout.write(f"  [DRY] CensusDecadalVintage decade={decade}")
            else:
                CensusDecadalVintage.objects.create(
                    decade=decade, effective_from=eff_from, effective_to=eff_to,
                )
            created += 1
        return created

    def _seed_acs(self, dry_run):
        from socialwarehouse.geo.models import ACSVintage

        created = 0
        latest_5year_end = max(ACS_5YEAR_ENDPOINTS)
        for end_year in ACS_5YEAR_ENDPOINTS:
            start_year = end_year - 4
            exists = ACSVintage.objects.filter(
                start_year=start_year, end_year=end_year, span_years=ACSVintage.SPAN_5YEAR,
            ).exists()
            if exists:
                continue
            eff_from = date(end_year, 12, 1)  # ACS 5-year typically released ~Dec of end-year+1
            eff_to = None if end_year == latest_5year_end else date(end_year + 1, 12, 1)
            if dry_run:
                self.stdout.write(f"  [DRY] ACSVintage 5-year {start_year}-{end_year}")
            else:
                ACSVintage.objects.create(
                    start_year=start_year, end_year=end_year,
                    span_years=ACSVintage.SPAN_5YEAR,
                    effective_from=eff_from, effective_to=eff_to,
                )
            created += 1

        latest_1year = max(ACS_1YEAR_YEARS)
        for year in ACS_1YEAR_YEARS:
            exists = ACSVintage.objects.filter(
                start_year=year, end_year=year, span_years=ACSVintage.SPAN_1YEAR,
            ).exists()
            if exists:
                continue
            eff_from = date(year, 9, 1)  # ACS 1-year typically released ~Sep of year+1
            eff_to = None if year == latest_1year else date(year + 1, 9, 1)
            if dry_run:
                self.stdout.write(f"  [DRY] ACSVintage 1-year {year}")
            else:
                ACSVintage.objects.create(
                    start_year=year, end_year=year,
                    span_years=ACSVintage.SPAN_1YEAR,
                    effective_from=eff_from, effective_to=eff_to,
                )
            created += 1
        return created

    def _seed_bls_qcew(self, dry_run):
        from socialwarehouse.geo.models import BLSQCEWVintage

        created = 0
        latest = max(BLS_QCEW_RANGE)
        for year, quarter in BLS_QCEW_RANGE:
            if BLSQCEWVintage.objects.filter(year=year, quarter=quarter).exists():
                continue
            eff_from = date(year, (quarter - 1) * 3 + 1, 1)
            next_year = year + (1 if quarter == 4 else 0)
            next_quarter_first_month = (quarter % 4) * 3 + 1
            eff_to = None if (year, quarter) == latest else date(
                next_year, next_quarter_first_month, 1
            )
            if dry_run:
                self.stdout.write(f"  [DRY] BLSQCEWVintage {year}Q{quarter}")
            else:
                BLSQCEWVintage.objects.create(
                    year=year, quarter=quarter,
                    effective_from=eff_from, effective_to=eff_to,
                )
            created += 1
        return created

    def _seed_bea_regional(self, dry_run):
        from socialwarehouse.geo.models import BEARegionalVintage

        created = 0
        latest = max(BEA_REGIONAL_YEARS)
        for year in BEA_REGIONAL_YEARS:
            if BEARegionalVintage.objects.filter(year=year).exists():
                continue
            eff_from = date(year, 1, 1)
            eff_to = None if year == latest else date(year + 1, 1, 1)
            if dry_run:
                self.stdout.write(f"  [DRY] BEARegionalVintage {year}")
            else:
                BEARegionalVintage.objects.create(
                    year=year, effective_from=eff_from, effective_to=eff_to,
                )
            created += 1
        return created

    def _seed_nces_school_year(self, dry_run):
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        created = 0
        latest = max(NCES_SCHOOL_YEARS)
        for start_year, end_year in NCES_SCHOOL_YEARS:
            exists = NCESSchoolYearVintage.objects.filter(
                start_year=start_year, end_year=end_year,
            ).exists()
            if exists:
                continue
            eff_from = date(start_year, 8, 1)  # academic year starts ~August
            eff_to = None if (start_year, end_year) == latest else date(end_year, 8, 1)
            if dry_run:
                self.stdout.write(
                    f"  [DRY] NCESSchoolYearVintage {start_year}-{str(end_year)[-2:]}"
                )
            else:
                NCESSchoolYearVintage.objects.create(
                    start_year=start_year, end_year=end_year,
                    effective_from=eff_from, effective_to=eff_to,
                )
            created += 1
        return created
