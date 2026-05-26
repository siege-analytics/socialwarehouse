"""
Silver Delta -> PostGIS star-schema materialization (SW#261).

Vendor-agnostic: runs against whatever's in silver.persons /
silver.person_scores / silver.vote_history regardless of source vendor.
TS-first since the importer thread ships TS data; L2 / Catalist / PDI
materialize automatically once their importers land.

Per `docs/architecture.md`: silver Delta is canonical; this module
projects silver into the PostGIS star schema (DimPerson / FactPersonScore
/ FactVoteHistory) that the Django web app and DRF API read.

Idempotency via Django ORM `bulk_create(update_conflicts=True)` on the
natural keys declared in #251's migration. Re-running materialize_all
on identical silver yields identical PostGIS state.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable, Iterator

from socialwarehouse.core.mixins import generate_entity_uuid5

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


# Vendor -> the matching JSONField name on DimPerson.
_VENDOR_EXTRAS_FIELD: dict[str, str] = {
    "pdi": "pdi_extras",
    "l2": "l2_extras",
    "catalist": "catalist_extras",
    "ts": "ts_extras",
}


def _chunked(iterable: Iterable, size: int) -> Iterator[list]:
    """Yield successive `size`-length chunks from `iterable`."""
    buf: list = []
    for item in iterable:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def _silver_persons_to_dimperson_kwargs(row) -> dict:
    """Map a silver.persons row (Spark Row or dict) to DimPerson kwargs.

    The vendor's extras map is dispatched into the matching JSONField
    (ts -> ts_extras, l2 -> l2_extras, etc.); the other three default
    to {}.

    `row` accepts both pyspark.sql.Row (asDict()) and plain dicts so
    the helper is pure-Python testable without Spark.
    """
    if hasattr(row, "asDict"):
        d = row.asDict()
    else:
        d = dict(row)

    vendor = d.get("vendor")
    extras = d.get("vendor_extras") or {}
    extras_field = _VENDOR_EXTRAS_FIELD.get(vendor)
    if extras_field is None:
        # Unknown vendor — log and stash extras nowhere; canonical fields
        # still ship.
        logger.warning(
            "DimPerson materialize: unknown vendor %r for vendor_voter_id=%r; "
            "vendor_extras dropped.", vendor, d.get("vendor_voter_id"),
        )
        extras_payload = {}
    else:
        extras_payload = {f: {} for f in _VENDOR_EXTRAS_FIELD.values()}
        extras_payload[extras_field] = dict(extras)

    vendor_voter_id = d.get("vendor_voter_id")
    kwargs = {
        "vendor": vendor,
        "vendor_voter_id": vendor_voter_id,
        # SourceAwareModel fields
        "data_source": d.get("data_source") or vendor or "",
        "jurisdiction_level": d.get("jurisdiction_level") or "state",
        "jurisdiction_state": d.get("jurisdiction_state") or d.get("registration_state") or "",
        "source_record_id": d.get("source_record_id") or vendor_voter_id or "",
        "ingested_at": d.get("ingested_at"),
        # IdentifiableModel field
        "entity_uuid": generate_entity_uuid5(vendor or "", vendor_voter_id or ""),
        "first_name": d.get("first_name") or "",
        "middle_name": d.get("middle_name") or "",
        "last_name": d.get("last_name") or "",
        "name_suffix": d.get("name_suffix") or "",
        "dob": d.get("dob"),
        "gender": d.get("gender") or "",
        "ethnicity": d.get("ethnicity") or "",
        "language": d.get("language") or "",
        "registration_status": d.get("registration_status") or "not_registered",
        "registration_state": d.get("registration_state") or "",
        "registration_date": d.get("registration_date"),
        "party_registration": d.get("party_registration") or "",
        "voter_status_reason": d.get("voter_status_reason") or "",
        "vendor_address_line1": d.get("address_line1") or "",
        "vendor_address_line2": d.get("address_line2") or "",
        "vendor_city": d.get("city") or "",
        "vendor_state": d.get("registration_state") or "",
        "vendor_zip": d.get("zip5") or "",
        "vendor_zip4": d.get("zip4") or "",
        "household_id": d.get("household_id") or "",
        "household_size": d.get("household_size"),
        "is_head_of_household": bool(d.get("is_head_of_household")),
        "general_election_count": int(d.get("general_election_count") or 0),
        "primary_election_count": int(d.get("primary_election_count") or 0),
        "total_vote_count": int(d.get("total_vote_count") or 0),
        "last_voted_at": d.get("last_voted_at"),
        "vote_frequency_category": d.get("vote_frequency_category") or "",
        "last_loaded_from_vendor": vendor or "",
        "silver_source_path": d.get("source_file") or "",
        **extras_payload,
    }
    return kwargs


def _build_id_lookup(person_keys: set[str]) -> dict[tuple[str, str], int]:
    """Resolve `vendor:vendor_voter_id` keys to DimPerson.id.

    Returns a {(vendor, vendor_voter_id): id} dict. Misses are absent
    from the dict; callers warn-and-skip per the documented contract.
    """
    from django.db.models import Q

    from socialwarehouse.warehouse.models import DimPerson

    if not person_keys:
        return {}

    # Parse person_key strings into (vendor, vendor_voter_id) pairs.
    pairs = [pk.split(":", 1) for pk in person_keys if ":" in pk]
    if not pairs:
        return {}

    # Group by vendor for efficient WHERE-IN per vendor.
    by_vendor: dict[str, list[str]] = {}
    for vendor, vid in pairs:
        by_vendor.setdefault(vendor, []).append(vid)

    qs_filter = Q()
    for vendor, vids in by_vendor.items():
        qs_filter |= Q(vendor=vendor, vendor_voter_id__in=vids)

    qs = DimPerson.objects.filter(qs_filter).values("id", "vendor", "vendor_voter_id")
    return {(r["vendor"], r["vendor_voter_id"]): r["id"] for r in qs}


# Update field lists. Exclude id and created_at; everything else is
# eligible for overwrite on conflict.
_DIMPERSON_UPDATE_FIELDS = [
    "data_source", "jurisdiction_level", "jurisdiction_state",
    "source_record_id", "ingested_at", "entity_uuid",
    "first_name", "middle_name", "last_name", "name_suffix", "dob", "gender",
    "ethnicity", "language",
    "registration_status", "registration_state", "registration_date",
    "party_registration", "voter_status_reason",
    "vendor_address_line1", "vendor_address_line2", "vendor_city",
    "vendor_state", "vendor_zip", "vendor_zip4",
    "household_id", "household_size", "is_head_of_household",
    "general_election_count", "primary_election_count", "total_vote_count",
    "last_voted_at", "vote_frequency_category",
    "pdi_extras", "l2_extras", "catalist_extras", "ts_extras",
    "last_loaded_from_vendor", "last_loaded_at", "silver_source_path",
    "updated_at",
]

_FACTPERSONSCORE_UPDATE_FIELDS = ["value", "scored_at"]
_FACTVOTEHISTORY_UPDATE_FIELDS = ["voted_method"]


def materialize_persons(
    spark: "SparkSession",
    silver_table_key: str = "silver.persons",
    batch_size: int = 10_000,
) -> int:
    """Read silver.persons and upsert DimPerson.

    Vendor-extras dispatched per row to the matching `*_extras`
    JSONField. Idempotent: re-running yields the same PostGIS state.

    Returns the number of silver rows processed (== upserted, modulo
    skipped rows on unknown vendor).
    """
    from datetime import datetime, timezone

    from socialwarehouse.delta.tables import TABLES
    from socialwarehouse.warehouse.models import DimPerson

    silver_path = TABLES[silver_table_key]["path"]
    df = spark.read.format("delta").load(silver_path)

    n_processed = 0
    for batch in _chunked(df.toLocalIterator(), batch_size):
        instances = []
        now = datetime.now(tz=timezone.utc)
        for row in batch:
            kwargs = _silver_persons_to_dimperson_kwargs(row)
            kwargs["last_loaded_at"] = now
            instances.append(DimPerson(**kwargs))
        if instances:
            DimPerson.objects.bulk_create(
                instances,
                update_conflicts=True,
                unique_fields=["vendor", "vendor_voter_id"],
                update_fields=_DIMPERSON_UPDATE_FIELDS,
                batch_size=batch_size,
            )
            n_processed += len(instances)

    logger.info("materialize_persons: upserted %d DimPerson rows.", n_processed)
    return n_processed


def _row_person_key(row) -> str:
    return row.person_key if hasattr(row, "person_key") else row["person_key"]


def materialize_scores(
    spark: "SparkSession",
    silver_table_key: str = "silver.person_scores",
    batch_size: int = 20_000,
) -> int:
    """Read silver.person_scores and upsert FactPersonScore.

    FK resolved per batch via DimPerson natural-key lookup. Rows
    pointing at a missing DimPerson are warned-and-skipped (see
    `materialize_all` for order enforcement).
    """
    from socialwarehouse.delta.tables import TABLES
    from socialwarehouse.warehouse.models import FactPersonScore

    silver_path = TABLES[silver_table_key]["path"]
    df = spark.read.format("delta").load(silver_path)

    n_upserted = 0
    n_skipped = 0
    for batch in _chunked(df.toLocalIterator(), batch_size):
        person_keys = {_row_person_key(r) for r in batch}
        id_lookup = _build_id_lookup(person_keys)

        instances = []
        for row in batch:
            d = row.asDict() if hasattr(row, "asDict") else dict(row)
            pk = d["person_key"]
            try:
                vendor, vid = pk.split(":", 1)
            except ValueError:
                n_skipped += 1
                continue
            person_id = id_lookup.get((vendor, vid))
            if person_id is None:
                n_skipped += 1
                continue
            instances.append(FactPersonScore(
                person_id=person_id,
                score_type=d["score_type"],
                value=d["value"],
                source_vendor=d["source_vendor"],
                methodology_version=d.get("methodology_version") or "",
                scored_at=d.get("scored_at"),
            ))
        if instances:
            FactPersonScore.objects.bulk_create(
                instances,
                update_conflicts=True,
                unique_fields=["person", "score_type", "source_vendor", "methodology_version"],
                update_fields=_FACTPERSONSCORE_UPDATE_FIELDS,
                batch_size=batch_size,
            )
            n_upserted += len(instances)

    if n_skipped:
        logger.warning(
            "materialize_scores: skipped %d rows because their DimPerson "
            "is not materialized. Run materialize_persons first.", n_skipped,
        )
    logger.info("materialize_scores: upserted %d FactPersonScore rows.", n_upserted)
    return n_upserted


def materialize_vote_history(
    spark: "SparkSession",
    silver_table_key: str = "silver.vote_history",
    batch_size: int = 50_000,
) -> int:
    """Read silver.vote_history and upsert FactVoteHistory.

    Same FK-resolution pattern as `materialize_scores`. Rows pointing
    at a missing DimPerson are warned-and-skipped.
    """
    from socialwarehouse.delta.tables import TABLES
    from socialwarehouse.warehouse.models import FactVoteHistory

    silver_path = TABLES[silver_table_key]["path"]
    df = spark.read.format("delta").load(silver_path)

    n_upserted = 0
    n_skipped = 0
    for batch in _chunked(df.toLocalIterator(), batch_size):
        person_keys = {_row_person_key(r) for r in batch}
        id_lookup = _build_id_lookup(person_keys)

        instances = []
        for row in batch:
            d = row.asDict() if hasattr(row, "asDict") else dict(row)
            pk = d["person_key"]
            try:
                vendor, vid = pk.split(":", 1)
            except ValueError:
                n_skipped += 1
                continue
            person_id = id_lookup.get((vendor, vid))
            if person_id is None:
                n_skipped += 1
                continue
            instances.append(FactVoteHistory(
                person_id=person_id,
                election_date=d["election_date"],
                election_type=d["election_type"],
                voted_method=d.get("voted_method") or "unknown",
                source_vendor=d["source_vendor"],
            ))
        if instances:
            FactVoteHistory.objects.bulk_create(
                instances,
                update_conflicts=True,
                unique_fields=["person", "election_date", "election_type", "source_vendor"],
                update_fields=_FACTVOTEHISTORY_UPDATE_FIELDS,
                batch_size=batch_size,
            )
            n_upserted += len(instances)

    if n_skipped:
        logger.warning(
            "materialize_vote_history: skipped %d rows because their "
            "DimPerson is not materialized. Run materialize_persons first.",
            n_skipped,
        )
    logger.info("materialize_vote_history: upserted %d FactVoteHistory rows.", n_upserted)
    return n_upserted


def materialize_all(spark: "SparkSession") -> dict[str, int]:
    """Run all three materializers in dependency order.

    Order matters: DimPerson must exist before FactPersonScore /
    FactVoteHistory because of the FK + the warn-and-skip-on-missing
    posture in the fact materializers.

    Returns per-table row counts.
    """
    counts = {
        "persons": materialize_persons(spark),
        "scores": materialize_scores(spark),
        "vote_history": materialize_vote_history(spark),
    }
    logger.info("materialize_all complete: %s", counts)
    return counts
