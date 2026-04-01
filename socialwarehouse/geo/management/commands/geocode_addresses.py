"""
Geocode ungeocoded addresses using Census Bureau + Nominatim.

Two-phase approach: Census batch API first (fast, high quality), then
Nominatim for misses (slower, approximate).

Usage:
    python manage.py geocode_addresses
    python manage.py geocode_addresses --batch-size 5000 --limit 10000
    python manage.py geocode_addresses --state TX
    python manage.py geocode_addresses --source census-only
    python manage.py geocode_addresses --dry-run
"""

import logging

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("socialwarehouse.geo")


class Command(BaseCommand):
    help = "Geocode ungeocoded addresses via Census Bureau batch API and/or Nominatim"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=5000,
            help="Addresses per Census batch request (max 10000, default 5000)",
        )
        parser.add_argument("--limit", type=int, default=0, help="Max addresses (0 = all)")
        parser.add_argument("--state", type=str, default=None, help="Filter by state abbreviation")
        parser.add_argument(
            "--source", type=str, default="dual",
            choices=["dual", "census-only", "nominatim-only"],
            help="Geocoding source strategy",
        )
        parser.add_argument("--nominatim-url", type=str, default=None, help="Custom Nominatim URL")
        parser.add_argument("--dry-run", action="store_true", help="Report counts only")
        parser.add_argument("--force", action="store_true", help="Re-geocode already geocoded")

    def handle(self, *args, **options):
        from siege_utilities.geo import (
            geocode_batch_chunked,
            use_nominatim_geocoder,
        )

        batch_size = min(options["batch_size"], 10_000)
        limit = options["limit"]
        state = options["state"]
        source = options["source"]
        nominatim_url = options["nominatim_url"]
        dry_run = options["dry_run"]
        force = options["force"]

        from socialwarehouse.geo.models import Address

        qs = Address.objects.all()
        if not force:
            qs = qs.filter(geocoded=False)
        if state:
            qs = qs.filter(state_abbreviation=state.upper())

        total = qs.count()
        process_count = min(limit, total) if limit else total

        self.stdout.write(
            f"Found {total} ungeocoded addresses"
            f"{f' in {state.upper()}' if state else ''}"
            f", will process {process_count}"
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] No changes made."))
            return

        if process_count == 0:
            self.stdout.write("Nothing to geocode.")
            return

        # Phase 1: Census batch geocoder
        census_matched = 0
        census_unmatched_ids = []

        if source in ("dual", "census-only"):
            self.stdout.write("Phase 1: Census batch geocoding...")

            batch_input = []
            address_map = {}
            addr_qs = qs[:limit] if limit else qs

            for addr in addr_qs.iterator():
                street = " ".join(filter(None, [
                    addr.primary_number, addr.street_name, addr.street_suffix,
                ]))
                batch_input.append({
                    "id": str(addr.pk),
                    "street": street,
                    "city": addr.city_name or "",
                    "state": addr.state_abbreviation or "",
                    "zipcode": addr.zip5 or "",
                })
                address_map[str(addr.pk)] = addr

            results = geocode_batch_chunked(batch_input, chunk_size=batch_size)

            for result in results:
                addr_pk = result.input_id
                if addr_pk not in address_map:
                    continue

                addr = address_map[addr_pk]
                if result.matched:
                    addr.latitude = result.lat
                    addr.longitude = result.lon
                    if result.lat and result.lon:
                        addr.geom = Point(result.lon, result.lat, srid=4326)
                    addr.geocoded = True
                    addr.geocode_source = "census"
                    addr.geocode_quality = result.match_type
                    addr.geocoded_at = timezone.now()
                    addr.assign_census_units_from_fips(
                        result.state_fips, result.county_fips,
                        result.tract, result.block,
                    )
                    addr.save()
                    census_matched += 1
                else:
                    census_unmatched_ids.append(addr_pk)

            self.stdout.write(
                f"Census: {census_matched} matched, {len(census_unmatched_ids)} unmatched"
            )

        # Phase 2: Nominatim fallback
        nominatim_matched = 0

        if source in ("dual", "nominatim-only"):
            if source == "nominatim-only":
                nominatim_addrs = list((qs[:limit] if limit else qs).iterator())
            else:
                nominatim_addrs = [
                    address_map[pk] for pk in census_unmatched_ids if pk in address_map
                ]

            if nominatim_addrs:
                self.stdout.write(f"Phase 2: Nominatim geocoding ({len(nominatim_addrs)} addresses)...")

                nom_kwargs = {}
                if nominatim_url:
                    nom_kwargs["server_url"] = nominatim_url

                for addr in nominatim_addrs:
                    query = ", ".join(filter(None, [
                        " ".join(filter(None, [
                            addr.primary_number, addr.street_name, addr.street_suffix,
                        ])),
                        addr.city_name,
                        addr.state_abbreviation,
                        addr.zip5,
                    ]))

                    if not query.strip():
                        continue

                    location = use_nominatim_geocoder(query, **nom_kwargs)

                    if location:
                        lat = float(location.latitude)
                        lon = float(location.longitude)
                        addr.latitude = lat
                        addr.longitude = lon
                        addr.geom = Point(lon, lat, srid=4326)
                        addr.geocoded = True
                        addr.geocode_source = "nominatim"
                        addr.geocode_quality = "Approximate"
                        addr.geocoded_at = timezone.now()
                        addr.save()
                        nominatim_matched += 1

                self.stdout.write(f"Nominatim: {nominatim_matched} matched")

        total_matched = census_matched + nominatim_matched
        self.stdout.write(self.style.SUCCESS(
            f"Done: {total_matched}/{process_count} geocoded "
            f"(Census: {census_matched}, Nominatim: {nominatim_matched}, "
            f"Failed: {process_count - total_matched})"
        ))
