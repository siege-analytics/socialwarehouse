"""
Load the warehouse star schema from siege_utilities boundary models and Census API.

Orchestrates DimensionLoaderService, CensusLoaderService, and
GeographicEnrichmentService in the correct order.

Usage:
    python manage.py load_warehouse
    python manage.py load_warehouse --year 2020 --state 06
    python manage.py load_warehouse --dimensions-only
    python manage.py load_warehouse --census-only --variables population income
    python manage.py load_warehouse --dry-run
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("socialwarehouse.warehouse")


class Command(BaseCommand):
    help = "Load warehouse star schema: dimensions → Census data → enrichment"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=2020, help="Census vintage year")
        parser.add_argument("--state", type=str, default=None, help="State FIPS code (e.g., 06)")
        parser.add_argument("--census-api-key", type=str, default=None)
        parser.add_argument("--dimensions-only", action="store_true", help="Load dimensions only")
        parser.add_argument("--census-only", action="store_true", help="Load Census facts only")
        parser.add_argument("--enrichment-only", action="store_true", help="Run enrichment only")
        parser.add_argument("--variables", nargs="+", default=None,
                            help="ACS variable groups (population, race, income, poverty, housing, education)")
        parser.add_argument("--crosswalk-from", type=int, default=None,
                            help="Apply crosswalk from this vintage (e.g., 2010)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        year = options["year"]
        state = options["state"]
        api_key = options["census_api_key"]
        dry_run = options["dry_run"]
        dims_only = options["dimensions_only"]
        census_only = options["census_only"]
        enrichment_only = options["enrichment_only"]
        variable_groups = options["variables"]
        crosswalk_from = options["crosswalk_from"]

        run_all = not (dims_only or census_only or enrichment_only)

        if dry_run:
            self.stdout.write(f"DRY RUN: Would load warehouse for vintage {year}")
            if state:
                self.stdout.write(f"  State: {state}")
            if variable_groups:
                self.stdout.write(f"  Variables: {variable_groups}")
            self.stdout.write(self.style.SUCCESS("[DRY RUN] No changes made."))
            return

        from socialwarehouse.warehouse.services.dimension_loader import DimensionLoaderService
        from socialwarehouse.warehouse.services.census_loader import CensusLoaderService
        from socialwarehouse.warehouse.services.geographic_enrichment import GeographicEnrichmentService

        # Step 1: Dimensions
        if run_all or dims_only:
            self.stdout.write(self.style.MIGRATE_HEADING("Step 1: Loading dimensions..."))
            dim_svc = DimensionLoaderService()

            geo_count = dim_svc.load_geography_from_siege(vintage_year=year)
            self.stdout.write(f"  DimGeography: {geo_count} records")

            time_count = dim_svc.load_time_dimension()
            self.stdout.write(f"  DimTime: {time_count} records")

            cycle_count = dim_svc.load_redistricting_cycles()
            self.stdout.write(f"  DimRedistrictingCycle: {cycle_count} records")

        # Step 2: Census facts
        if run_all or census_only:
            self.stdout.write(self.style.MIGRATE_HEADING("Step 2: Loading Census data..."))
            census_svc = CensusLoaderService(census_api_key=api_key)

            acs_count = census_svc.load_acs_estimates(
                vintage_year=year,
                summary_level="tract",
                state_fips=state,
                variable_groups=variable_groups,
            )
            self.stdout.write(f"  FactACSEstimate: {acs_count} rows")

            dec_count = census_svc.load_decennial_counts(
                census_year=year,
                summary_level="tract",
                state_fips=state,
            )
            self.stdout.write(f"  FactDecennialCount: {dec_count} rows")

        # Step 3: Enrichment
        if run_all or enrichment_only:
            self.stdout.write(self.style.MIGRATE_HEADING("Step 3: Enriching addresses..."))
            enrich_svc = GeographicEnrichmentService()

            demo_count = enrich_svc.enrich_with_demographics(
                vintage_year=year, state_fips=state,
            )
            self.stdout.write(f"  Demographics enrichment: {demo_count} addresses")

            urban_count = enrich_svc.classify_urbanicity(
                vintage_year=year, state_fips=state,
            )
            self.stdout.write(f"  Urbanicity classification: {urban_count} addresses")

            if crosswalk_from:
                cw_count = enrich_svc.apply_crosswalks(
                    source_year=crosswalk_from, target_year=year,
                )
                self.stdout.write(f"  Crosswalk ({crosswalk_from}→{year}): {cw_count} records")

        self.stdout.write(self.style.SUCCESS(f"Warehouse load complete (vintage={year})."))
