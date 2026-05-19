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

Memory + DB-discipline notes (M1/M2/M3 fixes, SW#145-#147):
  - Addresses are streamed via .iterator() in batches; no full materialization.
  - Per-batch results are flushed via bulk_update, not per-row .save().
  - No pre-loop qs.count() (which re-executes the SELECT when followed by
    iterator()); counts are reported post-loop from observed values.

See docs/entities/address.md for the canonical Address contract, the
chunked-iterator + bulk_update recipe, and the fixed-gotchas log.
"""

import logging

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("socialwarehouse.geo")


# Fields that Census or Nominatim phases may mutate. bulk_update touches
# only these; unchanged fields stay untouched. Order does not matter.
ADDRESS_BULK_UPDATE_FIELDS = [
    "latitude", "longitude", "geom",
    "geocoded", "geocode_source", "geocode_quality", "geocoded_at",
    "state_geoid", "county_geoid", "tract_geoid",
    "block_group_geoid", "block_geoid",
]

# Default Django bulk_update batching. Keeps single UPDATE statements
# bounded; tuned to roughly match the Census-API chunk shape.
DB_BULK_CHUNK = 500


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

        self.stdout.write(
            f"Geocoding ungeocoded addresses"
            f"{f' in {state.upper()}' if state else ''}"
            f"{f' (limit={limit})' if limit else ''}"
            f"..."
        )

        if dry_run:
            # For dry-run only, a single count is worth the query.
            dry_total = qs.count()
            dry_process = min(limit, dry_total) if limit else dry_total
            self.stdout.write(
                f"[DRY RUN] Would process {dry_process} of {dry_total} addresses. No changes made."
            )
            return

        # Tracking state. census_unmatched is now a list of Address objects
        # (not just pks) so Phase 2 doesn't need the in-memory address_map.
        census_processed = 0
        census_matched = 0
        census_unmatched = []  # list[Address]
        nominatim_processed = 0
        nominatim_matched = 0

        # Phase 1: Census batch geocoder. Streams chunks of addresses through
        # the batch API; flushes UPDATEs per chunk via bulk_update.
        if source in ("dual", "census-only"):
            self.stdout.write("Phase 1: Census batch geocoding...")

            addr_qs = qs[:limit] if limit else qs

            for addr_chunk in _yield_chunks(addr_qs.iterator(chunk_size=batch_size), batch_size):
                if not addr_chunk:
                    continue

                batch_input = []
                chunk_map = {}
                for addr in addr_chunk:
                    street = " ".join(filter(None, [
                        addr.primary_number, addr.street_name, addr.street_suffix,
                    ]))
                    pk_str = str(addr.pk)
                    batch_input.append({
                        "id": pk_str,
                        "street": street,
                        "city": addr.city_name or "",
                        "state": addr.state_abbreviation or "",
                        "zipcode": addr.zip5 or "",
                    })
                    chunk_map[pk_str] = addr

                results = geocode_batch_chunked(batch_input, chunk_size=batch_size)

                pending_updates = []
                for result in results:
                    addr = chunk_map.get(result.input_id)
                    if addr is None:
                        continue
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
                        pending_updates.append(addr)
                        census_matched += 1
                    else:
                        census_unmatched.append(addr)

                if pending_updates:
                    Address.objects.bulk_update(
                        pending_updates,
                        ADDRESS_BULK_UPDATE_FIELDS,
                        batch_size=DB_BULK_CHUNK,
                    )

                census_processed += len(addr_chunk)

            self.stdout.write(
                f"Census: processed {census_processed}, "
                f"matched {census_matched}, unmatched {len(census_unmatched)}"
            )

        # Phase 2: Nominatim fallback. Same streaming + bulk_update shape.
        if source in ("dual", "nominatim-only"):
            if source == "nominatim-only":
                nominatim_source = (qs[:limit] if limit else qs).iterator(chunk_size=batch_size)
            else:
                # In dual mode, the census_unmatched list IS our source. It
                # is already in memory because the Census phase had to map
                # results back to addresses. Stream it through the same
                # chunk-and-flush pattern for consistency.
                nominatim_source = iter(census_unmatched)

            self.stdout.write("Phase 2: Nominatim geocoding...")

            nom_kwargs = {}
            if nominatim_url:
                nom_kwargs["server_url"] = nominatim_url

            for addr_chunk in _yield_chunks(nominatim_source, DB_BULK_CHUNK):
                if not addr_chunk:
                    continue

                pending_updates = []
                for addr in addr_chunk:
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
                        pending_updates.append(addr)
                        nominatim_matched += 1

                if pending_updates:
                    Address.objects.bulk_update(
                        pending_updates,
                        ADDRESS_BULK_UPDATE_FIELDS,
                        batch_size=DB_BULK_CHUNK,
                    )

                nominatim_processed += len(addr_chunk)

            self.stdout.write(
                f"Nominatim: processed {nominatim_processed}, matched {nominatim_matched}"
            )

        total_processed = max(census_processed, nominatim_processed)
        total_matched = census_matched + nominatim_matched
        self.stdout.write(self.style.SUCCESS(
            f"Done: {total_matched}/{total_processed} geocoded "
            f"(Census: {census_matched}, Nominatim: {nominatim_matched}, "
            f"Failed: {total_processed - total_matched})"
        ))


def _yield_chunks(iterable, chunk_size):
    """Yield successive chunks of size <= chunk_size from any iterable.

    Caps memory at O(chunk_size). Each chunk is released for GC after the
    consumer is done with it (assuming no external references).
    """
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
