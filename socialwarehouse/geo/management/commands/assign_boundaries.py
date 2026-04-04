"""
Assign geographic boundaries to geocoded addresses via PostGIS spatial joins
using siege_utilities boundary models.

Usage:
    python manage.py assign_boundaries
    python manage.py assign_boundaries --year 2020 --state TX
    python manage.py assign_boundaries --batch-size 500 --limit 1000
    python manage.py assign_boundaries --dry-run
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("socialwarehouse.geo")


class Command(BaseCommand):
    help = "Assign census geographic boundaries to geocoded addresses via PostGIS spatial joins"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year", type=int, default=2020,
            help="Census vintage year for boundary assignment (default 2020)",
        )
        parser.add_argument(
            "--state", type=str, default=None,
            help="Filter by state abbreviation (e.g., TX)",
        )
        parser.add_argument(
            "--source", type=str, default=None,
            choices=["census", "nominatim", "smartystreets"],
            help="Filter by geocode source (default: all geocoded)",
        )
        parser.add_argument(
            "--batch-size", type=int, default=500,
            help="Addresses per batch (default 500)",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Max addresses to process (0 = all)",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Re-assign boundaries even if already assigned",
        )
        parser.add_argument(
            "--populate-fks", action="store_true",
            help="Also populate siege_geo ForeignKey references after assignment",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report counts without assigning",
        )

    def handle(self, *args, **options):
        year = options["year"]
        state = options["state"]
        source = options["source"]
        batch_size = options["batch_size"]
        limit = options["limit"]
        force = options["force"]
        populate_fks = options["populate_fks"]
        dry_run = options["dry_run"]

        from socialwarehouse.geo.models import Address

        qs = Address.objects.filter(geocoded=True, geom__isnull=False)

        if not force:
            qs = qs.filter(census_units_assigned_at__isnull=True)
        if state:
            qs = qs.filter(state_abbreviation=state.upper())
        if source:
            qs = qs.filter(geocode_source=source)

        total = qs.count()
        process_count = min(limit, total) if limit else total

        self.stdout.write(
            f"Found {total} addresses needing boundary assignment"
            f"{f' in {state.upper()}' if state else ''}"
            f"{f' (source: {source})' if source else ''}"
            f", will process {process_count}"
        )

        if dry_run:
            from django.db.models import Count
            state_counts = (
                qs.values("state_abbreviation")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )
            if state_counts:
                self.stdout.write("Top states:")
                for row in state_counts:
                    self.stdout.write(f"  {row['state_abbreviation']}: {row['count']}")
            self.stdout.write(self.style.SUCCESS("[DRY RUN] No changes made."))
            return

        if process_count == 0:
            self.stdout.write("Nothing to assign.")
            return

        from siege_utilities.geo.django.models import (
            State, County, Tract, BlockGroup,
            CongressionalDistrict, VTD,
            StateLegislativeLower, StateLegislativeUpper,
        )

        addr_ids = list(qs.values_list("pk", flat=True)[:limit] if limit else qs.values_list("pk", flat=True))

        assigned = 0
        failed = 0

        for i in range(0, len(addr_ids), batch_size):
            batch_ids = addr_ids[i:i + batch_size]
            batch_num = i // batch_size + 1
            batch_addrs = Address.objects.filter(pk__in=batch_ids)

            self.stdout.write(f"Batch {batch_num}: processing {len(batch_ids)} addresses...")

            for addr in batch_addrs:
                try:
                    if not addr.geom:
                        failed += 1
                        continue

                    # Transform to NAD83 (4269) for efficient spatial index use
                    # TIGER boundaries are stored at SRID 4269
                    query_point = addr.geom.clone()
                    query_point.transform(4269)

                    # Hierarchical spatial join using siege_geo models
                    s = State.objects.filter(
                        geom__contains=query_point, vintage_year=year
                    ).first()

                    if not s:
                        failed += 1
                        continue

                    addr.state_geoid = s.geoid

                    c = County.objects.filter(
                        geom__contains=query_point, vintage_year=year
                    ).first()
                    if c:
                        addr.county_geoid = c.geoid

                        t = Tract.objects.filter(
                            geom__contains=query_point, vintage_year=year
                        ).first()
                        if t:
                            addr.tract_geoid = t.geoid

                            bg = BlockGroup.objects.filter(
                                geom__contains=query_point, vintage_year=year
                            ).first()
                            if bg:
                                addr.block_group_geoid = bg.geoid

                        vtd = VTD.objects.filter(
                            geom__contains=query_point, vintage_year=year
                        ).first()
                        if vtd:
                            addr.vtd_geoid = vtd.geoid

                    cd = CongressionalDistrict.objects.filter(
                        geom__contains=query_point, vintage_year=year
                    ).first()
                    if cd:
                        addr.cd_geoid = cd.geoid

                    sldl = StateLegislativeLower.objects.filter(
                        geom__contains=query_point, vintage_year=year
                    ).first()
                    if sldl:
                        addr.sldl_geoid = sldl.geoid

                    sldu = StateLegislativeUpper.objects.filter(
                        geom__contains=query_point, vintage_year=year
                    ).first()
                    if sldu:
                        addr.sldu_geoid = sldu.geoid

                    addr.census_year = year
                    addr.census_units_assigned_at = timezone.now()
                    addr.save()

                    if populate_fks:
                        addr.populate_foreign_keys()

                    assigned += 1

                except Exception as e:
                    logger.error("Failed to assign boundaries for %s: %s", addr.pk, e)
                    failed += 1

            self.stdout.write(f"  Batch {batch_num} done: {assigned} assigned, {failed} failed")

        self.stdout.write(self.style.SUCCESS(
            f"Done: {assigned}/{process_count} assigned, {failed} failed (year={year})"
        ))
