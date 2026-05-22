"""
Address backfill: link silver.persons + DimPerson to canonical addresses.

Sub-issue B.5 of #250. Companion to B.4 (#261 / PR #264), which
materialized DimPerson with `address` left null.

Looks up `sw_geo.Address` rows whose lat/lon match the vendor-supplied
lat/lon on silver.persons (within a configurable tolerance), then
updates both:

- silver.persons.address_id (Delta) via DeltaTable.merge so the
  silver canonical view records the linkage.
- DimPerson.address_id (PostGIS) so the Django web app picks up
  geo.Address records directly.

Matching strategy: lat/lon range match with a small tolerance
(default 0.00001 degrees ~= ~1m at the equator). Avoids depending on
sw_geo.Address.geom being populated; works on rows where only the
DecimalField lat/lon are set. If geom is populated, this still works
because the underlying lat/lon must match for geom to be consistent.

If multiple Address rows match within tolerance (e.g. multi-unit
buildings sharing a Census-block centroid), the lowest-id match wins
deterministically and a warning is logged. The "right" answer for
multi-unit addresses is a follow-on if real-world data shows it.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


# Default tolerance ~= 1m at the equator. Caller can pass a different
# value if real-world TS lat/lon precision warrants it. Anything tighter
# than ~1e-6 degrees risks rejecting legitimate matches due to upstream
# float rounding; anything looser starts conflating neighboring parcels.
DEFAULT_TOLERANCE_DEGREES = 0.00001


def _find_address_id(
    lat: float,
    lon: float,
    tolerance: float = DEFAULT_TOLERANCE_DEGREES,
) -> int | None:
    """Return the lowest-id sw_geo.Address whose lat/lon is within tolerance.

    Returns None if no match. Multi-match yields a warning + the
    lowest-id winner.
    """
    from socialwarehouse.geo.models import Address

    lat_min = Decimal(str(lat - tolerance))
    lat_max = Decimal(str(lat + tolerance))
    lon_min = Decimal(str(lon - tolerance))
    lon_max = Decimal(str(lon + tolerance))

    candidates = list(
        Address.objects
        .filter(
            latitude__gte=lat_min, latitude__lte=lat_max,
            longitude__gte=lon_min, longitude__lte=lon_max,
        )
        .values_list("id", flat=True)
        .order_by("id")[:5]
    )
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning(
            "Address backfill: %d candidates within tolerance %f at "
            "(%f, %f); picking lowest-id %d. Tighten tolerance or "
            "model multi-unit addresses if this is wrong.",
            len(candidates), tolerance, lat, lon, candidates[0],
        )
    return candidates[0]


def _resolve_addresses(
    rows: list[dict],
    tolerance: float,
) -> dict[str, int]:
    """For each input row, look up the matching Address.

    Returns {person_key: address_id} for the rows that matched.
    """
    out: dict[str, int] = {}
    for r in rows:
        lat = r.get("latitude")
        lon = r.get("longitude")
        if lat is None or lon is None:
            continue
        addr_id = _find_address_id(float(lat), float(lon), tolerance)
        if addr_id is not None:
            out[r["person_key"]] = addr_id
    return out


def backfill_addresses(
    spark: "SparkSession",
    silver_table_key: str = "silver.persons",
    tolerance: float = DEFAULT_TOLERANCE_DEGREES,
    batch_size: int = 10_000,
) -> dict[str, int]:
    """Backfill silver.persons.address_id and DimPerson.address.

    Args:
        spark: Active SparkSession with Delta extensions.
        silver_table_key: Registry key for silver.persons.
        tolerance: Degrees tolerance for lat/lon match (default ~= 1m).
        batch_size: Rows per batch for the silver-iteration + DB lookup.

    Returns:
        dict with `silver_updated` (rows where address_id was set on
        silver.persons) and `postgis_updated` (DimPerson rows where
        address_id was set).
    """
    from delta.tables import DeltaTable
    from pyspark.sql.types import (
        LongType,
        StringType,
        StructField,
        StructType,
    )

    from socialwarehouse.delta.tables import TABLES
    from socialwarehouse.warehouse.models import DimPerson

    silver_path = TABLES[silver_table_key]["path"]
    df = (
        spark.read.format("delta").load(silver_path)
        .filter("address_id IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL")
        .select("vendor", "vendor_voter_id", "person_key", "latitude", "longitude")
    )

    total_silver = 0
    total_postgis = 0
    update_schema = StructType([
        StructField("person_key", StringType(), False),
        StructField("new_address_id", LongType(), False),
    ])
    silver_table = DeltaTable.forPath(spark, silver_path)

    for batch in _chunk(df.toLocalIterator(), batch_size):
        rows = [r.asDict() if hasattr(r, "asDict") else dict(r) for r in batch]
        resolved = _resolve_addresses(rows, tolerance)
        if not resolved:
            continue

        # ── Update silver.persons.address_id via merge ──
        updates = [
            {"person_key": pk, "new_address_id": int(aid)}
            for pk, aid in resolved.items()
        ]
        updates_df = spark.createDataFrame(updates, schema=update_schema)
        (
            silver_table.alias("t")
            .merge(updates_df.alias("u"), "t.person_key = u.person_key")
            .whenMatchedUpdate(set={"address_id": "u.new_address_id"})
            .execute()
        )
        total_silver += len(updates)

        # ── Update DimPerson.address via Django ORM ──
        # Build (vendor, vendor_voter_id) -> address_id map and bulk-update.
        # bulk_update requires loaded instances; for a backfill of this
        # shape that's fine (one query per batch).
        natural_keys = [
            (r["vendor"], r["vendor_voter_id"])
            for r in rows
            if r["person_key"] in resolved
        ]
        if not natural_keys:
            continue
        from django.db.models import Q
        q = Q()
        for v, vid in natural_keys:
            q |= Q(vendor=v, vendor_voter_id=vid)
        persons = list(DimPerson.objects.filter(q))
        for p in persons:
            p.address_id = resolved.get(f"{p.vendor}:{p.vendor_voter_id}")
        DimPerson.objects.bulk_update(persons, ["address_id"], batch_size=batch_size)
        total_postgis += len(persons)

    counts = {"silver_updated": total_silver, "postgis_updated": total_postgis}
    logger.info("backfill_addresses complete: %s", counts)
    return counts


def _chunk(it, size: int):
    """Mirror of materialize._chunked; local copy to avoid circular import."""
    buf: list = []
    for item in it:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
