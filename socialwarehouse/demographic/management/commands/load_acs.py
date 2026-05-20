"""Load ACS estimates into the warehouse via siege_utilities.geo.census.api.CensusAPI.

Per D Q3, the API client is upstream (SU has it). This command:
  1. Resolves a Vintage row for the (dataset, year) combination.
  2. Fetches the variable subset for the given (state, geography) via SU's
     CensusAPI.fetch_data — returns a pandas DataFrame.
  3. Walks the DataFrame and writes ACSEstimate rows.

Usage:
    python manage.py load_acs --vintage 2019-2023 --state 06 \\
        --geography tract --variables B01001_001E,B19013_001E

    python manage.py load_acs --vintage 2019-2023 --state 06 \\
        --geography county
    # (no --variables = use the seeded curated catalog)

Idempotent: re-running clears+rewrites the (vintage, variable, boundary_type,
geoid) slice that the command would write.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


logger = logging.getLogger(__name__)


# Map Census API geography names to Address._BOUNDARY_TYPES tokens.
GEOGRAPHY_TO_BOUNDARY_TYPE = {
    "state": "state",
    "county": "county",
    "tract": "tract",
    "block group": "block_group",
    "block": "block",
    "place": "place",
    "zcta": "zcta",
    "zip code tabulation area": "zcta",
}


class Command(BaseCommand):
    help = "Load ACS estimates into ACSEstimate via siege_utilities CensusAPI."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vintage", type=str, required=True,
            help=(
                "Vintage name: '2019-2023' for 5-year, '2023' for 1-year. "
                "Must match an ACSVintage row's `name` column."
            ),
        )
        parser.add_argument(
            "--state", type=str, required=True,
            help="2-digit state FIPS code (e.g., '06' for CA).",
        )
        parser.add_argument(
            "--geography", type=str, default="county",
            help="Census API geography (county / tract / block group / place / zcta).",
        )
        parser.add_argument(
            "--county", type=str, default=None,
            help="Optional 3-digit county FIPS to scope tract / block-group queries.",
        )
        parser.add_argument(
            "--variables", type=str, default=None,
            help=(
                "Comma-separated variable codes (e.g. 'B01001_001E,B19013_001E'). "
                "Default: all variables currently in the ACSVariable catalog."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch + report counts without writing.",
        )

    def handle(self, *args, **options):
        from socialwarehouse.demographic.models import ACSEstimate, ACSVariable
        from socialwarehouse.geo.models import ACSVintage

        vintage_name = options["vintage"]
        state_fips = options["state"]
        geography = options["geography"]
        county_fips = options["county"]
        variables_arg = options["variables"]
        dry_run = options["dry_run"]

        # Resolve vintage.
        try:
            vintage = ACSVintage.objects.get(name=vintage_name)
        except ACSVintage.DoesNotExist:
            raise CommandError(
                f"No ACSVintage with name={vintage_name!r}. "
                f"Available: {list(ACSVintage.objects.values_list('name', flat=True))}"
            )

        # Resolve year + dataset string for the Census API.
        if vintage.span_years == ACSVintage.SPAN_5YEAR:
            dataset = "acs5"
            api_year = vintage.end_year
        else:
            dataset = "acs1"
            api_year = vintage.start_year

        # Resolve variables.
        if variables_arg:
            var_codes = [v.strip() for v in variables_arg.split(",") if v.strip()]
        else:
            var_codes = list(
                ACSVariable.objects.values_list("variable_code", flat=True).order_by("variable_code")
            )
            if not var_codes:
                raise CommandError(
                    "No ACSVariable rows in the catalog. Run `seed_acs_variables` first, "
                    "or pass --variables explicitly."
                )

        # Map Census geography string to boundary_type token.
        boundary_type = GEOGRAPHY_TO_BOUNDARY_TYPE.get(
            geography.lower(), geography.lower().replace(" ", "_")
        )

        self.stdout.write(
            f"Fetching {dataset} year={api_year} state={state_fips} "
            f"geography={geography} variables={len(var_codes)}"
        )

        df = self._fetch_via_su(
            variables=var_codes, year=api_year, dataset=dataset,
            geography=geography, state_fips=state_fips, county_fips=county_fips,
        )
        if df is None or df.empty:
            self.stdout.write(self.style.WARNING("Census API returned no rows."))
            return

        self.stdout.write(f"Census returned {len(df)} rows; writing to ACSEstimate...")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write up to {len(df) * len(var_codes)} ACSEstimate rows."
            ))
            return

        # Look up ACSVariable rows we'll need.
        var_lookup = {v.variable_code: v for v in ACSVariable.objects.filter(variable_code__in=var_codes)}
        unknown = set(var_codes) - set(var_lookup)
        if unknown:
            self.stdout.write(self.style.WARNING(
                f"Skipping {len(unknown)} variable codes not in ACSVariable catalog: "
                f"{sorted(unknown)[:5]}{'...' if len(unknown) > 5 else ''}"
            ))

        written = 0
        with transaction.atomic():
            for _, row in df.iterrows():
                geoid = self._row_geoid(row)
                if not geoid:
                    continue
                for var_code in var_codes:
                    var = var_lookup.get(var_code)
                    if var is None:
                        continue
                    value, moe, annotation = self._extract_value_moe(row, var_code)
                    ACSEstimate.objects.update_or_create(
                        vintage=vintage,
                        variable=var,
                        boundary_type=boundary_type,
                        geoid=geoid,
                        defaults={
                            "value": value,
                            "moe": moe,
                            "annotation": annotation,
                        },
                    )
                    written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} ACSEstimate rows for vintage={vintage.name} "
            f"boundary_type={boundary_type} state={state_fips}."
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_via_su(self, *, variables, year, dataset, geography, state_fips, county_fips):
        """Call siege_utilities CensusAPI; return the DataFrame.

        Defensive about import + transient API failures: returns None on either,
        with a warning on stdout.
        """
        try:
            from siege_utilities.geo.census import CensusAPI
        except ImportError as exc:
            raise CommandError(
                f"siege_utilities.geo.census.CensusAPI not importable: {exc}. "
                f"Confirm SU is installed in this environment."
            )

        client = CensusAPI()
        try:
            return client.fetch_data(
                variables=variables,
                year=year,
                dataset=dataset,
                geography=geography,
                state_fips=state_fips,
                county_fips=county_fips,
                include_moe=True,
            )
        except Exception as exc:
            logger.exception("Census API fetch failed: %s", exc)
            self.stdout.write(self.style.ERROR(f"Census API fetch failed: {exc}"))
            return None

    def _row_geoid(self, row):
        """Extract GEOID from a SU-fetched DataFrame row.

        SU's _process_response constructs a `GEOID` column for every supported
        geography. If absent (older SU version, edge case), fall through.
        """
        return row.get("GEOID") or ""

    def _extract_value_moe(self, row, var_code):
        """Pull (value, moe, annotation) from a row for one variable code.

        Census variables ending in 'E' have a sibling MOE column ending in 'M'.
        Census jam values ('*', '**', '-', etc.) come through as strings — store
        them in `annotation` and leave value=None.
        """
        raw_value = row.get(var_code)
        moe_code = var_code[:-1] + "M" if var_code.endswith("E") else None
        raw_moe = row.get(moe_code) if moe_code else None

        value, annotation = self._to_decimal_or_annotation(raw_value)
        moe, _ = self._to_decimal_or_annotation(raw_moe)
        return value, moe, annotation

    @staticmethod
    def _to_decimal_or_annotation(raw):
        if raw is None:
            return None, ""
        # Pandas NaN
        try:
            if hasattr(raw, "__class__") and raw.__class__.__name__ == "float" and raw != raw:
                return None, ""
        except Exception:
            pass
        try:
            return Decimal(str(raw)), ""
        except (InvalidOperation, ValueError):
            return None, str(raw)
