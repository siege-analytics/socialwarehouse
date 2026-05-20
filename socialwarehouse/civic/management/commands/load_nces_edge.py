"""Load NCES EDGE per-district demographic estimates (Phase 1c).

EDGE re-publishes ACS-derived estimates aggregated to school-district
boundaries (which ACS itself doesn't directly publish). This command
loads one EDGE release into NCESDistrictEDGEDemographics rows.

Usage:
    python manage.py load_nces_edge --vintage 2022-23 --acs-endpoint 2018-22 --state 06
    python manage.py load_nces_edge --vintage 2022-23 --acs-endpoint 2018-22 --state 06 --dry-run

The school-year vintage anchors the WAREHOUSE side (matching CCD's
cadence); the --acs-endpoint identifies which ACS 5-year release
EDGE used as its source.
"""

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Load NCES EDGE per-district demographic estimates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vintage", type=str, required=True,
            help="NCESSchoolYearVintage name like '2022-23'. The warehouse-side anchor.",
        )
        parser.add_argument(
            "--acs-endpoint", type=str, required=True,
            help="EDGE source ACS endpoint like '2018-22' (5-year endpoint range).",
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
        from socialwarehouse.civic.models import NCESDistrictEDGEDemographics
        from socialwarehouse.civic.services.nces_files import NCESFiles
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        vintage_name = options["vintage"]
        acs_endpoint = options["acs_endpoint"]
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

        self.stdout.write(
            f"EDGE district demographics vintage={vintage.name} "
            f"acs_endpoint={acs_endpoint} state={state_fips}"
        )

        files = NCESFiles()
        df = files.load_edge_district_demographics(acs_endpoint)

        # State filter — EDGE uses STATEFP or STATEFIPS depending on release.
        state_col = "STATEFP" if "STATEFP" in df.columns else (
            "STATEFIPS" if "STATEFIPS" in df.columns else None
        )
        if state_col:
            df = df[df[state_col] == state_fips]

        self.stdout.write(f"Parsed {len(df)} EDGE rows for state {state_fips}.")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write up to {len(df)} EDGE demographic rows."
            ))
            return

        written = 0
        with transaction.atomic():
            for _, row in df.iterrows():
                leaid = str(row.get("LEAID", "")).strip()
                if not leaid:
                    continue

                NCESDistrictEDGEDemographics.objects.update_or_create(
                    vintage=vintage,
                    geoid=leaid,
                    defaults={
                        "boundary_type": "school_district",
                        "state_fips": str(row.get(state_col, "")) if state_col else "",
                        "source_acs_endpoint": acs_endpoint,
                        **self._extract_demographics(row),
                    },
                )
                written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} EDGE demographic rows for {vintage.name} state={state_fips}."
        ))

    @staticmethod
    def _extract_demographics(row):
        # EDGE column names evolve across releases; check both forms.
        # Use _first to avoid `or` short-circuit treating 0 as missing.
        child_5_17 = _to_int(_first(row, "CHILD_5_17", "TOT_CHLD"))
        in_poverty = _to_int(_first(row, "IPR_LT100_5_17", "IPR100_5_17"))
        return {
            "total_population": _to_int(row.get("TOT")),
            "population_5_17": child_5_17,
            "population_under_5": _to_int(_first(row, "CHILD_LT5", "CHILD_UNDER_5")),
            "pop_5_17_white_nh": _to_int(row.get("WHITE_NH_5_17")),
            "pop_5_17_black_nh": _to_int(row.get("BLACK_NH_5_17")),
            "pop_5_17_asian_nh": _to_int(row.get("ASIAN_NH_5_17")),
            "pop_5_17_aian_nh": _to_int(row.get("AIAN_NH_5_17")),
            "pop_5_17_nhpi_nh": _to_int(row.get("NHPI_NH_5_17")),
            "pop_5_17_two_or_more_nh": _to_int(row.get("TWO_NH_5_17")),
            "pop_5_17_hispanic": _to_int(row.get("HISPANIC_5_17")),
            "pop_5_17_in_poverty": in_poverty,
            "pop_5_17_poverty_rate": _to_rate(in_poverty, child_5_17),
            "households_total": _to_int(_first(row, "HH_TOT", "TOTAL_HH")),
            "households_with_school_age": _to_int(row.get("HH_WITH_CHILDREN")),
            "median_household_income": _to_int(_first(row, "MEDIAN_HH_INC", "MEDIAN_HH_INCOME")),
            "pop_5_17_english_at_home": _to_int(row.get("ENGLISH_5_17")),
            "pop_5_17_other_lang_at_home": _to_int(row.get("OTHER_LANG_5_17")),
            "pop_5_17_foreign_born": _to_int(row.get("FOREIGN_BORN_5_17")),
        }


def _first(row, *keys):
    """Return row[keys[0]] if present (not None / not NaN), else row[keys[1]], etc.

    Distinct from `row.get(a) or row.get(b)` because that treats 0 as
    missing — 0 is a valid Census count and must not fall through.
    """
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        if isinstance(v, float) and v != v:  # NaN
            continue
        return v
    return None


def _to_int(raw):
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and raw != raw:
            return None
        val = int(Decimal(str(raw)))
        if val < 0:
            return None
        return val
    except Exception:
        return None


def _to_rate(numerator, denominator):
    """Compute a 0.0-1.0 rate; None if either component is missing or denom is zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))
