"""
Export PostGIS address data to Delta Lake bronze tier.

Bridges the Django/PostGIS world with the Spark/Delta Lake world.
Use this to seed the lakehouse from PostGIS data, then run Spark-based
enrichment for warehouse-scale operations.

Usage:
    python manage.py export_to_delta
    python manage.py export_to_delta --batch-size 50000
    python manage.py export_to_delta --dry-run
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("socialwarehouse.delta")


class Command(BaseCommand):
    help = "Export PostGIS addresses to Delta Lake bronze tier"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=100_000,
            help="JDBC fetch size (default 100000)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report count without exporting",
        )

    def handle(self, *args, **options):
        from socialwarehouse.geo.models import Address

        total = Address.objects.count()
        self.stdout.write(f"PostGIS addresses: {total:,}")

        if options["dry_run"]:
            from socialwarehouse.delta.enrichment import estimate_scale
            engine, reason = estimate_scale(total)
            self.stdout.write(f"Recommended engine: {engine} ({reason})")
            self.stdout.write(self.style.SUCCESS("[DRY RUN] No export performed."))
            return

        if total == 0:
            self.stdout.write("No addresses to export.")
            return

        from socialwarehouse.delta.config import get_spark_session
        from socialwarehouse.delta.enrichment import load_postgis_addresses_to_delta

        spark = get_spark_session()
        count = load_postgis_addresses_to_delta(spark, batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"Exported {count:,} addresses to Delta Lake bronze tier"))
