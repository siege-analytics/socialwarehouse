"""Seed the curated PL 94-171 (redistricting) decennial variable catalog.

Per D Phase 3, ship a small subset of the PL file that's the most-asked-for
in electoral contexts. The DHC follow-up will fold in additional curated
DHC variables later.

Idempotent. Rerunnable.
"""

from django.core.management.base import BaseCommand
from django.db import transaction


# (variable_code, table_code, concept, label, universe, dataset)
CURATED_VARIABLES = [
    ("P1_001N", "P1", "RACE", "Total:", "Total population", "pl"),
    ("P1_003N", "P1", "RACE", "Total:!!Population of one race:!!White alone",
     "Total population", "pl"),
    ("P1_004N", "P1", "RACE",
     "Total:!!Population of one race:!!Black or African American alone",
     "Total population", "pl"),
    ("P1_005N", "P1", "RACE",
     "Total:!!Population of one race:!!American Indian and Alaska Native alone",
     "Total population", "pl"),
    ("P1_006N", "P1", "RACE", "Total:!!Population of one race:!!Asian alone",
     "Total population", "pl"),
    ("P2_001N", "P2", "HISPANIC OR LATINO, AND NOT HISPANIC OR LATINO BY RACE",
     "Total:", "Total population", "pl"),
    ("P2_002N", "P2", "HISPANIC OR LATINO, AND NOT HISPANIC OR LATINO BY RACE",
     "Total:!!Hispanic or Latino", "Total population", "pl"),
    ("P2_005N", "P2", "HISPANIC OR LATINO, AND NOT HISPANIC OR LATINO BY RACE",
     "Total:!!Not Hispanic or Latino:!!Population of one race:!!White alone",
     "Total population", "pl"),
    ("P3_001N", "P3", "RACE FOR THE POPULATION 18 YEARS AND OVER",
     "Total:", "Population 18 years and over", "pl"),
    ("P4_001N", "P4",
     "HISPANIC OR LATINO, AND NOT HISPANIC OR LATINO BY RACE "
     "FOR THE POPULATION 18 YEARS AND OVER",
     "Total:", "Population 18 years and over", "pl"),
    ("H1_001N", "H1", "OCCUPANCY STATUS", "Total:", "Housing units", "pl"),
    ("H1_002N", "H1", "OCCUPANCY STATUS", "Total:!!Occupied",
     "Housing units", "pl"),
    ("H1_003N", "H1", "OCCUPANCY STATUS", "Total:!!Vacant",
     "Housing units", "pl"),
]


class Command(BaseCommand):
    help = "Seed the curated PL 94-171 decennial variable catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from socialwarehouse.demographic.models import DecennialVariable

        dry_run = options["dry_run"]
        created = 0
        with transaction.atomic():
            for (code, table, concept, label, universe, dataset) in CURATED_VARIABLES:
                if DecennialVariable.objects.filter(variable_code=code).exists():
                    continue
                if not dry_run:
                    DecennialVariable.objects.create(
                        variable_code=code, table_code=table,
                        concept=concept, label=label,
                        universe=universe, dataset=dataset,
                    )
                created += 1
            if dry_run:
                transaction.set_rollback(True)

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} decennial variables."))
