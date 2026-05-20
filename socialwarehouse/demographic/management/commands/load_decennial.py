"""Load decennial Census counts via siege_utilities.geo.census.api.CensusAPI.

Per D Phase 3 — full count, no MOE. Mirrors load_acs but targets
DecennialCount + DecennialVariable and uses `dec/pl` (or `dec/dhc`) as
the API dataset.

Usage:
    python manage.py load_decennial --vintage 2020 --state 06 \\
        --geography county
    python manage.py load_decennial --vintage 2020 --state 06 \\
        --geography tract --dataset pl --variables P1_001N,P2_001N
"""

import logging
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


logger = logging.getLogger(__name__)


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
    help = "Load decennial Census counts into DecennialCount via siege_utilities CensusAPI."

    def add_arguments(self, parser):
        parser.add_argument("--vintage", type=str, required=True,
            help="Vintage name like '2020'. Must match a CensusDecadalVintage row.")
        parser.add_argument("--state", type=str, required=True,
            help="2-digit state FIPS.")
        parser.add_argument("--geography", type=str, default="county")
        parser.add_argument("--county", type=str, default=None)
        parser.add_argument("--dataset", type=str, default="pl",
            help="Decennial sub-dataset: 'pl' (default) or 'dhc'.")
        parser.add_argument("--variables", type=str, default=None,
            help="Comma-separated decennial variable codes; default = all in catalog "
                 "matching --dataset.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from socialwarehouse.demographic.models import DecennialCount, DecennialVariable
        from socialwarehouse.geo.models import CensusDecadalVintage

        vintage_name = options["vintage"]
        state_fips = options["state"]
        geography = options["geography"]
        county_fips = options["county"]
        dataset = options["dataset"]
        variables_arg = options["variables"]
        dry_run = options["dry_run"]

        try:
            vintage = CensusDecadalVintage.objects.get(name=vintage_name)
        except CensusDecadalVintage.DoesNotExist:
            raise CommandError(
                f"No CensusDecadalVintage with name={vintage_name!r}. "
                f"Available: "
                f"{list(CensusDecadalVintage.objects.values_list('name', flat=True))}"
            )

        if variables_arg:
            var_codes = [v.strip() for v in variables_arg.split(",") if v.strip()]
        else:
            var_codes = list(
                DecennialVariable.objects.filter(dataset=dataset)
                .values_list("variable_code", flat=True).order_by("variable_code")
            )
            if not var_codes:
                raise CommandError(
                    f"No DecennialVariable rows for dataset={dataset!r}. "
                    "Run `seed_decennial_variables` first or pass --variables."
                )

        boundary_type = GEOGRAPHY_TO_BOUNDARY_TYPE.get(
            geography.lower(), geography.lower().replace(" ", "_")
        )

        api_dataset = f"dec/{dataset}"
        self.stdout.write(
            f"Fetching {api_dataset} year={vintage.year} state={state_fips} "
            f"geography={geography} variables={len(var_codes)}"
        )

        df = self._fetch_via_su(
            variables=var_codes, year=vintage.year, dataset=api_dataset,
            geography=geography, state_fips=state_fips, county_fips=county_fips,
        )
        if df is None or df.empty:
            self.stdout.write(self.style.WARNING("Census API returned no rows."))
            return

        self.stdout.write(f"Census returned {len(df)} rows; writing to DecennialCount...")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY] would write up to {len(df) * len(var_codes)} DecennialCount rows."
            ))
            return

        var_lookup = {
            v.variable_code: v for v in
            DecennialVariable.objects.filter(variable_code__in=var_codes)
        }
        unknown = set(var_codes) - set(var_lookup)
        if unknown:
            self.stdout.write(self.style.WARNING(
                f"Skipping {len(unknown)} unknown variable codes: "
                f"{sorted(unknown)[:5]}{'...' if len(unknown) > 5 else ''}"
            ))

        written = 0
        with transaction.atomic():
            for _, row in df.iterrows():
                geoid = row.get("GEOID") or ""
                if not geoid:
                    continue
                for var_code in var_codes:
                    var = var_lookup.get(var_code)
                    if var is None:
                        continue
                    value, annotation = self._to_int_or_annotation(row.get(var_code))
                    DecennialCount.objects.update_or_create(
                        vintage=vintage,
                        variable=var,
                        boundary_type=boundary_type,
                        geoid=geoid,
                        defaults={"value": value, "annotation": annotation},
                    )
                    written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} DecennialCount rows for vintage={vintage.name} "
            f"boundary_type={boundary_type} state={state_fips}."
        ))

    def _fetch_via_su(self, *, variables, year, dataset, geography, state_fips, county_fips):
        try:
            from siege_utilities.geo.census import CensusAPI
        except ImportError as exc:
            raise CommandError(
                f"siege_utilities.geo.census.CensusAPI not importable: {exc}."
            )
        client = CensusAPI()
        try:
            return client.fetch_data(
                variables=variables, year=year, dataset=dataset,
                geography=geography, state_fips=state_fips, county_fips=county_fips,
                include_moe=False,
            )
        except Exception as exc:
            logger.exception("Census API fetch failed: %s", exc)
            self.stdout.write(self.style.ERROR(f"Census API fetch failed: {exc}"))
            return None

    @staticmethod
    def _to_int_or_annotation(raw):
        if raw is None:
            return None, ""
        try:
            if raw.__class__.__name__ == "float" and raw != raw:
                return None, ""
        except Exception:
            pass
        try:
            return int(Decimal(str(raw))), ""
        except (InvalidOperation, ValueError):
            return None, str(raw)[:10]
