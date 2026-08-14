"""LoC / congress-legislators -> civic-ontology Person materialization (#73).

Idempotently upserts into the *existing* ontology models (no bespoke
tables): the Agent hub + Person subtype + EntityIdentifier rows +
one canonical Attestation carrying the source record + Office / OfficeTerm
for congressional service.

Mirrors `swh/voters/materialize.py`: pure-Python row mappers live in
`swh/loc/mappings.py`; Django ORM writes happen here with Django imported
lazily inside functions so the mappers import without a configured Django.
Idempotency comes from deterministic UUID5 keys + `update_or_create`:
re-running on identical input yields identical rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from swh.loc import mappings

logger = logging.getLogger(__name__)

# core/attestation.py constants (kept local to avoid a Django import here).
ENTITY_SUBTYPE_PERSON = "person"
ATTESTATION_KIND_ENTITY_RESOLUTION = "entity_resolution"
TIER_AUTHORITATIVE = "authoritative"


def _ensure_django() -> None:
    """Configure Django once, mirroring swh/reconcile.py."""
    import django

    if not django.apps.apps.ready:
        django.setup()


def _upsert_person(rec: dict, now: datetime):
    """Create/refresh Agent + Person + identifiers + bio attestation.

    Returns the Person's ``entity_uuid`` (UUID5), or None when the record
    has no bioguide id (the identity anchor) and is therefore skipped.
    """
    from socialwarehouse.agents.models import Person
    from socialwarehouse.core.agent import Agent
    from socialwarehouse.core.attestation import Attestation
    from socialwarehouse.core.mixins import generate_entity_uuid5
    from socialwarehouse.core.models import EntityIdentifier

    bg = mappings.bioguide_id(rec)
    if not bg:
        return None

    person_uuid = generate_entity_uuid5(mappings.LOC_DATA_SOURCE, bg)
    agent_uuid = Agent.make_entity_uuid("person", mappings.LOC_DATA_SOURCE, bg)

    agent, _ = Agent.objects.get_or_create(
        entity_uuid=agent_uuid,
        defaults={
            "subtype": "person",
            "data_source": mappings.LOC_DATA_SOURCE,
            "source_record_id": bg,
            "jurisdiction_level": "federal",
        },
    )

    Person.objects.update_or_create(
        entity_uuid=person_uuid,
        defaults={**mappings.person_kwargs(rec), "ingested_at": now, "agent": agent},
    )

    for ident in mappings.identifiers(rec):
        EntityIdentifier.register(
            person_uuid,
            ident["identifier_type"],
            ident["identifier_value"],
            ident["data_source"],
            jurisdiction_level="federal",
        )

    values = mappings.bio_attestation_values(rec)
    Attestation.objects.update_or_create(
        entity_id=person_uuid,
        entity_subtype=ENTITY_SUBTYPE_PERSON,
        attestation_kind=ATTESTATION_KIND_ENTITY_RESOLUTION,
        is_canonical=True,
        defaults={
            "attested_values": values,
            "attested_values_hash": mappings.content_hash(values),
            "attestation_source_tier": TIER_AUTHORITATIVE,
            "attested_at": now,
            "data_source": mappings.LOC_DATA_SOURCE,
            "source_record_id": bg,
            "jurisdiction_level": "federal",
        },
    )
    return person_uuid


def _upsert_terms(rec: dict, person_uuid) -> int:
    """Upsert the Person's congressional Offices + OfficeTerms. Returns count."""
    from socialwarehouse.core.mixins import generate_entity_uuid5
    from socialwarehouse.political.models import Office, OfficeTerm

    n = 0
    for term in mappings.terms(rec):
        o = term["office"]
        office, _ = Office.objects.get_or_create(
            jurisdiction_level=o["jurisdiction_level"],
            jurisdiction_state=o["jurisdiction_state"],
            chamber=o["chamber"],
            district_number=o["district_number"],
            defaults={
                "name": o["name"],
                "entity_uuid": generate_entity_uuid5(
                    "office",
                    o["jurisdiction_level"],
                    o["jurisdiction_state"],
                    o["chamber"],
                    o["district_number"],
                ),
                "data_source": mappings.LOC_DATA_SOURCE,
            },
        )
        OfficeTerm.objects.update_or_create(
            office=office,
            person_uuid=person_uuid,
            start_date=term["start_date"],
            defaults={
                "end_date": term["end_date"],
                "term_type": term["term_type"],
                "congress_number": term["congress_number"],
                "data_source": mappings.LOC_DATA_SOURCE,
            },
        )
        n += 1
    return n


def materialize_legislators(records, batch_size: int = 500) -> dict:
    """Upsert a sequence of congress-legislators records into the ontology.

    Idempotent (deterministic UUID5 keys + update_or_create). Records with
    no bioguide id are skipped. Returns per-kind counts.
    """
    _ensure_django()
    from django.db import transaction

    now = datetime.now(tz=timezone.utc)
    n_person = n_terms = n_skipped = 0
    buf = list(records)
    for i in range(0, len(buf), batch_size):
        chunk = buf[i : i + batch_size]
        with transaction.atomic():
            for rec in chunk:
                person_uuid = _upsert_person(rec, now)
                if person_uuid is None:
                    n_skipped += 1
                    continue
                n_person += 1
                n_terms += _upsert_terms(rec, person_uuid)

    counts = {"persons": n_person, "office_terms": n_terms, "skipped": n_skipped}
    logger.info("materialize_legislators: %s", counts)
    return counts
