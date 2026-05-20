"""Load NCES CCD district-level aggregates (Phase 1a).

Combines the three CCD files (Directory + Nonfiscal + Finance) into
NCESDistrictAggregate rows per LEA per school year. Phase 1b will
add school-level; Phase 1c will add EDGE demographic estimates.

Usage:
    python manage.py load_nces --vintage 2022-23 --state 06
    python manage.py load_nces --vintage 2022-23 --state 06 --dry-run

Uses socialwarehouse.civic.services.nces_files.NCESFiles for the
download/parse — SU#534 tracks lifting that to SU.
"""

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


# NCES agency-type codes (CCD Directory file).
# 1 = Regular local school district. 2 = Local school district that's part
# of a supervisory union. 3 = Supervisory union admin. 4 = Regional or
# state-level admin. 5 = State-operated agency. 6 = Federal-operated. 7 = Charter.
# 8 = Other. (per NCES CCD documentation)
AGENCY_TYPE_TO_DISTRICT_TYPE = {
    "1": "unified",  # most "regular" districts are unified K-12 in CCD shorthand
    "2": "unified",
    "3": "other",
    "4": "other",
    "5": "other",
    "6": "other",
    "7": "other",  # charter
    "8": "other",
}


class Command(BaseCommand):
    help = "Load NCES CCD district-level aggregates into NCESDistrictAggregate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vintage", type=str, required=True,
            help="School-year vintage name like '2022-23'. Must match NCESSchoolYearVintage.",
        )
        parser.add_argument(
            "--state", type=str, required=True,
            help="2-digit state FIPS code; filters CCD rows to this state.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch + report counts without writing.",
        )

    def handle(self, *args, **options):
        from socialwarehouse.civic.models import NCESDistrictAggregate
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

        self.stdout.write(f"NCES vintage={vintage.name} state={state_fips}")

        files = NCESFiles()
        directory = files.load_ccd_directory(vintage.name)
        nonfiscal = files.load_ccd_nonfiscal(vintage.name)
        finance = files.load_ccd_finance(vintage.name)

        # Filter to state.
        if "STATEFIPS" in directory.columns:
            directory = directory[directory["STATEFIPS"] == state_fips]
        directory = directory.set_index("LEAID", drop=False)
        nonfiscal = nonfiscal.set_index("LEAID", drop=False) if "LEAID" in nonfiscal.columns else nonfiscal
        finance = finance.set_index("LEAID", drop=False) if "LEAID" in finance.columns else finance

        self.stdout.write(
            f"Parsed {len(directory)} LEAs / {len(nonfiscal)} nonfiscal rows / "
            f"{len(finance)} finance rows for state {state_fips}."
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write up to {len(directory)} NCESDistrictAggregate rows."
            ))
            return

        written = 0
        with transaction.atomic():
            for leaid, dir_row in directory.iterrows():
                nf = nonfiscal.loc[leaid] if leaid in nonfiscal.index else None
                fi = finance.loc[leaid] if leaid in finance.index else None

                NCESDistrictAggregate.objects.update_or_create(
                    vintage=vintage,
                    geoid=leaid,
                    defaults={
                        "boundary_type": "school_district",
                        "state_fips": str(dir_row.get("STATEFIPS", "")),
                        "district_type": AGENCY_TYPE_TO_DISTRICT_TYPE.get(
                            str(dir_row.get("AGCHRT", "")), "other",
                        ),
                        # Nonfiscal: enrollment + staff
                        **self._extract_nonfiscal(nf),
                        # Finance: revenues + expenditures
                        **self._extract_finance(fi),
                    },
                )
                written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} NCESDistrictAggregate rows for {vintage.name} state={state_fips}."
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
            "teachers_fte": _to_decimal(row.get("TOTTCH")),
        }

    @staticmethod
    def _extract_finance(row):
        if row is None:
            return {}
        return {
            "revenue_total": _to_int(row.get("TOTALREV")),
            "revenue_federal": _to_int(row.get("TFEDREV")),
            "revenue_federal_title_i": _to_int(row.get("C14")),
            "revenue_federal_idea": _to_int(row.get("C15")),
            "revenue_federal_child_nutrition": _to_int(row.get("C25")),
            "revenue_state": _to_int(row.get("TSTREV")),
            "revenue_state_formula": _to_int(row.get("STR")),
            "revenue_state_compensatory": _to_int(row.get("C01")),
            "revenue_state_special_ed": _to_int(row.get("C04")),
            "revenue_local": _to_int(row.get("TLOCREV")),
            "revenue_local_property_tax": _to_int(row.get("T06")),
            "expenditure_total": _to_int(row.get("TOTALEXP")),
            "expenditure_instruction": _to_int(row.get("TCURINST")),
            "expenditure_support_services": _to_int(row.get("TCURSSVC")),
            "expenditure_food_services": _to_int(row.get("E11")),
            "expenditure_capital_outlay": _to_int(row.get("TCAPOUT")),
            "expenditure_per_pupil": _to_int(row.get("PPCSTOT")),
            "long_term_debt_outstanding": _to_int(row.get("_50LFND")),
        }


def _to_int(raw):
    if raw is None:
        return None
    try:
        # Pandas NaN check
        if isinstance(raw, float) and raw != raw:
            return None
        val = int(Decimal(str(raw)))
        # NCES uses negative sentinel codes (-1, -2, -3, -9) for missing/suppressed.
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


def _sum_grades(row, columns):
    total = 0
    found_any = False
    for col in columns:
        v = _to_int(row.get(col))
        if v is not None:
            total += v
            found_any = True
    return total if found_any else None
