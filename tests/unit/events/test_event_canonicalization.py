from datetime import date

import pytest
from django.test import TestCase

from socialwarehouse.core.attestation import Attestation
from socialwarehouse.events.models import Event


def _mk_event(**kw):
    defaults = dict(event_type="transaction", event_date=date(2024, 3, 1), data_source="fec")
    defaults.update(kw)
    return Event.objects.create(**defaults)


@pytest.mark.django_db
class TestEventCanonicalization(TestCase):
    def test_canonicalization_defaults(self):
        e = _mk_event()
        assert e.canonical_attestation is None
        assert e.attestation_disagreement is False
        assert e.is_amended is False
        assert e.amendment_count == 0
        assert e.event_state == "active"
        # Existing behavior preserved: year derived from event_date.
        assert e.year == 2024

    def test_canonical_attestation_cache_links_to_attestation(self):
        e = _mk_event()
        att = Attestation.objects.create(
            entity_id=e.event_uuid,
            entity_subtype="event",
            attestation_kind="fec",
            data_source="fec",
            is_canonical=True,
        )
        e.canonical_attestation = att
        e.save(update_fields=["canonical_attestation"])
        e.refresh_from_db()
        assert e.canonical_attestation == att
        # Reverse accessor from Attestation.
        assert att.canonical_for_events.first() == e

    def test_canonical_attestation_set_null_on_delete(self):
        e = _mk_event()
        att = Attestation.objects.create(
            entity_id=e.event_uuid, entity_subtype="event", attestation_kind="fec", data_source="fec"
        )
        e.canonical_attestation = att
        e.save(update_fields=["canonical_attestation"])
        att.delete()
        e.refresh_from_db()
        # Event survives; cache cleared (truth lives on Attestation.is_canonical).
        assert e.canonical_attestation is None

    def test_amendment_tracking(self):
        e = _mk_event()
        e.is_amended = True
        e.amendment_count = 2
        e.event_state = "amended"
        e.save(update_fields=["is_amended", "amendment_count", "event_state"])
        e.refresh_from_db()
        assert e.is_amended is True
        assert e.amendment_count == 2
        assert e.event_state == "amended"

    def test_attestation_disagreement_flag(self):
        e = _mk_event(attestation_disagreement=True)
        assert e.attestation_disagreement is True
