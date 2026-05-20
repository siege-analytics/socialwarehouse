"""Load NCES CCD school-level aggregates (Phase 1b).

Joins the school-level CCD files (Directory + Nonfiscal) into
NCESSchoolAggregate rows per NCESSCH per school year.

Usage:
    python manage.py load_nces_schools --vintage 2022-23 --state 06
    python manage.py load_nces_schools --vintage 2022-23 --state 06 --dry-run
"""

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


# NCES CCD school-type code mapping (per CCD documentation).
SCHOOL_TYPE_MAPPING = {
    "1": "regular",
    "2": "special",
    "3": "vocational",
    "4": "alternative",
}

# School status codes (NCES SCHOOL_STATUS / SY_STATUS field).
SCHOOL_STATUS_MAPPING = {
    "1": "open",
    "2": "closed",
    "3": "new",
    "4": "added",
    "5": "changed_boundary",
    "6": "inactive",
    "7": "future",
    "8": "reopened",
}


class Command(BaseCommand):
    help = "Load NCES CCD school-level aggregates into NCESSchoolAggregate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vintage", type=str, required=True,
            help="School-year vintage name like '2022-23'. Must match NCESSchoolYearVintage.",
        )
        parser.add_argument(
            "--state", type=str, required=True,
            help="2-digit state FIPS; filters rows to this state.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch + report counts without writing.",
        )

    def handle(self, *args, **options):
        from socialwarehouse.civic.models import NCESSchoolAggregate
        from socialwarehouse.civic.services.nces_files import NCESFiles
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        vintage_name = options["vintage"]
        state_fips = options["state"]
        dry_run = options["dry_run"]

        try:
            vintage = NCESSchoolYearVintage.objects.get(name=vintage_name)
        except NCESSchoolYearVintage.DoesNotExist:
            raise CommandError(
                f"No NCESSchoolYearVintage with name={vintage_name!r}. "
                f"Available: "
                f"{list(NCESSchoolYearVintage.objects.values_list('name', flat=True)[:5])}…"
            )

        self.stdout.write(f"NCES schools vintage={vintage.name} state={state_fips}")

        files = NCESFiles()
        directory = files.load_ccd_school_directory(vintage.name)
        nonfiscal = files.load_ccd_school_nonfiscal(vintage.name)

        if "STATEFIPS" in directory.columns:
            directory = directory[directory["STATEFIPS"] == state_fips]
        directory = directory.set_index("NCESSCH", drop=False)
        if "NCESSCH" in nonfiscal.columns:
            nonfiscal = nonfiscal.set_index("NCESSCH", drop=False)

        self.stdout.write(
            f"Parsed {len(directory)} schools / {len(nonfiscal)} nonfiscal rows for state {state_fips}."
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write up to {len(directory)} NCESSchoolAggregate rows."
            ))
            return

        written = 0
        with transaction.atomic():
            for nces_id, dir_row in directory.iterrows():
                nf = nonfiscal.loc[nces_id] if nces_id in nonfiscal.index else None

                NCESSchoolAggregate.objects.update_or_create(
                    vintage=vintage,
                    geoid=nces_id,
                    defaults={
                        "boundary_type": "school",
                        "leaid": str(dir_row.get("LEAID", "")),
                        "state_fips": str(dir_row.get("STATEFIPS", "")),
                        "school_name": str(dir_row.get("SCH_NAME", ""))[:255],
                        "school_type": SCHOOL_TYPE_MAPPING.get(
                            str(dir_row.get("SCH_TYPE", "")), "other",
                        ),
                        "school_status": SCHOOL_STATUS_MAPPING.get(
                            str(dir_row.get("SY_STATUS", "")), "",
                        ),
                        "is_charter": _to_bool(dir_row.get("CHARTER_TEXT")),
                        "is_magnet": _to_bool(dir_row.get("MAGNET_TEXT")),
                        "is_title_i": _to_bool(dir_row.get("TITLEI_STATUS")),
                        "grade_low": str(dir_row.get("GSLO", ""))[:4],
                        "grade_high": str(dir_row.get("GSHI", ""))[:4],
                        **self._extract_nonfiscal(nf),
                    },
                )
                written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} NCESSchoolAggregate rows for {vintage.name} state={state_fips}."
        ))

    @staticmethod
    def _extract_nonfiscal(row):
        if row is None:
            return {}
        return {
            "enrollment_total": _to_int(row.get("TOTAL")),
            "enrollment_pk_grade_k": _sum_grades(row, ["PK", "KG"]),
            "enrollment_grade_1_5": _sum_grades(row, [f"G{n:02d}" for n in range(1, 6)]),
            "enrollment_grade_6_8": _sum_grades(row, ["G06", "G07", "G08"]),
            "enrollment_grade_9_12": _sum_grades(row, ["G09", "G10", "G11", "G12"]),
            "free_lunch_eligible_count": _to_int(row.get("TOTFRL")),
            "teachers_fte": _to_decimal(row.get("FTE")),
        }


def _to_int(raw):
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and raw != raw:
            return None
        val = int(Decimal(str(raw)))
        # NCES negative sentinels for missing/suppressed.
        if val < 0:
            return None
        return val
    except Exception:
        return None


def _to_decimal(raw):
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and raw != raw:
            return None
        val = Decimal(str(raw))
        if val < 0:
            return None
        return val
    except Exception:
        return None


def _to_bool(raw):
    """NCES uses 'Yes' / 'No' / '1' / '2' / missing for booleans depending on field."""
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if s in ("YES", "1", "TRUE", "Y"):
        return True
    if s in ("NO", "2", "FALSE", "N"):
        return False
    return None


def _sum_grades(row, columns):
    total = 0
    found_any = False
    for col in columns:
        v = _to_int(row.get(col))
        if v is not None:
            total += v
            found_any = True
    return total if found_any else None
