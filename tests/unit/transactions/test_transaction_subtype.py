import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.test import TestCase

from socialwarehouse.core.attestation import Attestation
from socialwarehouse.events.models import Event, EventParticipant
from socialwarehouse.transactions.models import Contribution, Transaction


def _mk_transaction_event():
    return Event.objects.create(
        event_type="transaction", event_date=date(2024, 5, 2), data_source="fec"
    )


@pytest.mark.django_db
class TestTransactionSubtype(TestCase):
    def test_transaction_is_event_subtype_detail(self):
        e = _mk_transaction_event()
        txn = Transaction.objects.create(
            event=e,
            transaction_subtype="contribution",
            amount=Decimal("250.00"),
            transaction_date=date(2024, 5, 2),
        )
        assert txn.currency == "USD"
        assert txn.transaction_subtype == "contribution"
        # First-class subtype treatment: reverse one-to-one accessor on Event,
        # mirroring corporate_detail / electoral_detail.
        assert e.transaction_detail == txn

    def test_transaction_subtype_choices(self):
        for sub in ("contribution", "expenditure", "transfer", "obligation"):
            e = _mk_transaction_event()
            txn = Transaction.objects.create(
                event=e, transaction_subtype=sub, amount=Decimal("1.00"), transaction_date=date(2024, 5, 2)
            )
            assert txn.transaction_subtype == sub

    def test_existing_record_links_to_canonical_event(self):
        e = _mk_transaction_event()
        c = Contribution.objects.create(
            from_agent_uuid=uuid.uuid4(),
            from_agent_type="person",
            to_agent_uuid=uuid.uuid4(),
            to_agent_type="committee",
            amount=Decimal("250.00"),
            transaction_date=date(2024, 5, 2),
            data_source="fec",
            event=e,
        )
        c.refresh_from_db()
        assert c.event == e
        # %(class)s reverse accessor on the Event.
        assert e.contribution_records.first() == c

    def test_existing_record_event_link_nullable(self):
        # Backward-compatible: the link is optional.
        c = Contribution.objects.create(
            from_agent_uuid=uuid.uuid4(),
            from_agent_type="person",
            to_agent_uuid=uuid.uuid4(),
            to_agent_type="committee",
            amount=Decimal("50.00"),
            transaction_date=date(2024, 5, 2),
            data_source="fec",
        )
        assert c.event is None

    def test_event_participants_shared_bridge(self):
        # Transaction parties recorded through the shared EventParticipant
        # bridge (payer = source, payee = target).
        e = _mk_transaction_event()
        Transaction.objects.create(
            event=e, transaction_subtype="contribution", amount=Decimal("250.00"), transaction_date=date(2024, 5, 2)
        )
        payer = uuid.uuid4()
        payee = uuid.uuid4()
        EventParticipant.objects.create(event=e, agent_uuid=payer, agent_type="person", role_in_event="source")
        EventParticipant.objects.create(event=e, agent_uuid=payee, agent_type="committee", role_in_event="target")
        assert e.participants.count() == 2
        assert e.participants.filter(role_in_event="source").first().agent_uuid == payer

    def test_canonical_attestation_cache_vs_truth(self):
        # Event.canonical_attestation is the fast-lookup cache; the source of
        # truth is Attestation.is_canonical (one canonical per entity/kind).
        e = _mk_transaction_event()
        Transaction.objects.create(
            event=e, transaction_subtype="contribution", amount=Decimal("250.00"), transaction_date=date(2024, 5, 2)
        )
        canonical = Attestation.objects.create(
            entity_id=e.event_uuid,
            entity_subtype="event",
            attestation_kind="fec",
            data_source="fec",
            is_canonical=True,
        )
        e.canonical_attestation = canonical
        e.save(update_fields=["canonical_attestation"])
        # Cache and truth agree.
        truth = Attestation.canonical_for("event", e.event_uuid, "fec")
        assert truth == canonical
        assert e.canonical_attestation == truth
