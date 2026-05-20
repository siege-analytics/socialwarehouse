"""Seed the small curated ACS variable catalog.

Per D Q1, the long-term plan is the full ~30K catalog via
`fetch_acs_variables` (Phase 1b — fetches from Census's
variables.json endpoint). For Phase 1a, this command ships a small
curated subset of the most-asked-for variables so the warehouse is
immediately useful and tests don't need network.

Idempotent. Rerunnable.
"""

from django.core.management.base import BaseCommand
from django.db import transaction


# Curated subset for Phase 1a. Each tuple:
# (variable_code, table_code, concept, label, universe, predicate_type)
CURATED_VARIABLES = [
    (
        "B01001_001E", "B01001",
        "SEX BY AGE",
        "Estimate!!Total:",
        "Total population", "int",
    ),
    (
        "B01002_001E", "B01002",
        "MEDIAN AGE BY SEX",
        "Estimate!!Median age --!!Total:",
        "Total population", "float",
    ),
    (
        "B19013_001E", "B19013",
        "MEDIAN HOUSEHOLD INCOME IN THE PAST 12 MONTHS",
        "Estimate!!Median household income in the past 12 months",
        "Households", "int",
    ),
    (
        "B25001_001E", "B25001",
        "HOUSING UNITS",
        "Estimate!!Total",
        "Housing units", "int",
    ),
    (
        "B25003_002E", "B25003",
        "TENURE",
        "Estimate!!Total:!!Owner occupied",
        "Occupied housing units", "int",
    ),
    (
        "B25003_003E", "B25003",
        "TENURE",
        "Estimate!!Total:!!Renter occupied",
        "Occupied housing units", "int",
    ),
    (
        "B17001_002E", "B17001",
        "POVERTY STATUS IN THE PAST 12 MONTHS BY SEX BY AGE",
        "Estimate!!Total:!!Income in the past 12 months below poverty level:",
        "Population for whom poverty status is determined", "int",
    ),
    (
        "B15003_022E", "B15003",
        "EDUCATIONAL ATTAINMENT FOR THE POPULATION 25 YEARS AND OVER",
        "Estimate!!Total:!!Bachelor's degree",
        "Population 25 years and over", "int",
    ),
    (
        "B15003_023E", "B15003",
        "EDUCATIONAL ATTAINMENT FOR THE POPULATION 25 YEARS AND OVER",
        "Estimate!!Total:!!Master's degree",
        "Population 25 years and over", "int",
    ),
    (
        "B03002_003E", "B03002",
        "HISPANIC OR LATINO ORIGIN BY RACE",
        "Estimate!!Total:!!Not Hispanic or Latino:!!White alone",
        "Total population", "int",
    ),
    (
        "B03002_004E", "B03002",
        "HISPANIC OR LATINO ORIGIN BY RACE",
        "Estimate!!Total:!!Not Hispanic or Latino:!!Black or African American alone",
        "Total population", "int",
    ),
    (
        "B03002_012E", "B03002",
        "HISPANIC OR LATINO ORIGIN BY RACE",
        "Estimate!!Total:!!Hispanic or Latino:",
        "Total population", "int",
    ),
]


class Command(BaseCommand):
    help = "Seed the Phase 1a curated ACS variable catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be created without writing.",
        )

    def handle(self, *args, **options):
        from socialwarehouse.demographic.models import ACSVariable

        dry_run = options["dry_run"]
        created = 0
        with transaction.atomic():
            for (var_code, table_code, concept, label, universe, ptype) in CURATED_VARIABLES:
                if ACSVariable.objects.filter(variable_code=var_code).exists():
                    continue
                if dry_run:
                    self.stdout.write(f"  [DRY] {var_code} ({concept})")
                else:
                    ACSVariable.objects.create(
                        variable_code=var_code,
                        table_code=table_code,
                        concept=concept,
                        label=label,
                        universe=universe,
                        predicate_type=ptype,
                    )
                created += 1
            if dry_run:
                transaction.set_rollback(True)

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} ACS variables."))
