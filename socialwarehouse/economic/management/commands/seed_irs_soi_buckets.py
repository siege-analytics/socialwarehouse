"""Seed the standard 6 IRS SOI AGI buckets for an IRSSOIVintage.

Per E Q3 = (a), buckets are vintage-scoped. This command seeds the
standard 6-bin layout used for recent SOI releases (TY2019+). For
older / future vintages with different bin boundaries, pass
--bucket-spec to override.

Idempotent per (vintage, bucket_code).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# IRS SOI standard 6-bucket layout (TY2019+). (code, label, lower, upper).
# Open-ended bounds use None.
STANDARD_BUCKETS = [
    (1, "Under $25,000",                       None,    25_000),
    (2, "$25,000 under $50,000",            25_000,    50_000),
    (3, "$50,000 under $75,000",            50_000,    75_000),
    (4, "$75,000 under $100,000",           75_000,   100_000),
    (5, "$100,000 under $200,000",         100_000,   200_000),
    (6, "$200,000 or more",                200_000,      None),
]


class Command(BaseCommand):
    help = "Seed standard IRS SOI AGI buckets for a given IRSSOIVintage."

    def add_arguments(self, parser):
        parser.add_argument("--vintage", type=str, required=True,
            help="IRSSOIVintage name, e.g. 'TY2022'.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from socialwarehouse.economic.models import IRSSOIIncomeBucket
        from socialwarehouse.geo.models import IRSSOIVintage

        vintage_name = options["vintage"]
        dry_run = options["dry_run"]

        try:
            vintage = IRSSOIVintage.objects.get(name=vintage_name)
        except IRSSOIVintage.DoesNotExist:
            raise CommandError(
                f"No IRSSOIVintage with name={vintage_name!r}."
            )

        created = 0
        with transaction.atomic():
            for (code, label, lo, hi) in STANDARD_BUCKETS:
                if IRSSOIIncomeBucket.objects.filter(vintage=vintage, bucket_code=code).exists():
                    continue
                if not dry_run:
                    IRSSOIIncomeBucket.objects.create(
                        vintage=vintage, bucket_code=code, label=label,
                        lower_bound=lo, upper_bound=hi,
                    )
                created += 1
            if dry_run:
                transaction.set_rollback(True)

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {created} IRS SOI buckets for {vintage.name}."
        ))
