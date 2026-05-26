"""Cross-model query tests for the ontology.

These tests verify the shared query surface works: agents linked by
UUID across transactions and events, the event participant bridge,
and temporal queries across models.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import models
from django.test import TestCase

from socialwarehouse.core.mixins import generate_entity_uuid4, generate_entity_uuid5


@pytest.mark.django_db
class TestSharedQuerySurface(TestCase):
    """Agent UUID links span across transaction and event tables."""

    def setUp(self):
        self.donor_uuid = generate_entity_uuid5("John", "Doe", "1980-01-01")
        self.committee_uuid = generate_entity_uuid5("Friends of Progress", "TX")

    def test_contributions_by_agent_uuid(self):
        from socialwarehouse.transactions.models import Contribution

        Contribution.objects.create(
            from_agent_uuid=self.donor_uuid,
            from_agent_type="person",
            to_agent_uuid=self.committee_uuid,
            to_agent_type="committee",
            amount=Decimal("500.00"),
            transaction_date=date(2024, 3, 15),
        )
        Contribution.objects.create(
            from_agent_uuid=self.donor_uuid,
            from_agent_type="person",
            to_agent_uuid=self.committee_uuid,
            to_agent_type="committee",
            amount=Decimal("1000.00"),
            transaction_date=date(2024, 6, 1),
        )
        qs = Contribution.objects.filter(from_agent_uuid=self.donor_uuid)
        assert qs.count() == 2
        assert qs.aggregate(total=models.Sum("amount"))["total"] == Decimal("1500.00")

    def test_events_by_agent_uuid(self):
        from socialwarehouse.events.models import Event, EventParticipant

        e = Event.objects.create(
            event_type="transaction",
            event_date=date(2024, 3, 15),
        )
        EventParticipant.objects.create(
            event=e,
            agent_uuid=self.donor_uuid,
            agent_type="person",
            role_in_event="source",
        )
        qs = EventParticipant.objects.filter(agent_uuid=self.donor_uuid)
        assert qs.count() == 1
        assert qs.first().event.event_type == "transaction"

    def test_all_events_for_agent_across_types(self):
        from socialwarehouse.events.models import Event, EventParticipant

        e1 = Event.objects.create(
            event_type="transaction",
            event_date=date(2024, 3, 15),
        )
        e2 = Event.objects.create(
            event_type="electoral",
            event_date=date(2024, 11, 5),
        )
        for event in [e1, e2]:
            EventParticipant.objects.create(
                event=event,
                agent_uuid=self.committee_uuid,
                agent_type="committee",
                role_in_event="target" if event == e1 else "candidate",
            )
        events = Event.objects.filter(
            participants__agent_uuid=self.committee_uuid,
        ).distinct()
        assert events.count() == 2
        types = set(events.values_list("event_type", flat=True))
        assert types == {"transaction", "electoral"}


@pytest.mark.django_db
class TestEventAutoYear(TestCase):
    """Event.save() auto-derives year from event_date."""

    def test_year_derived_on_save(self):
        from socialwarehouse.events.models import Event

        e = Event.objects.create(
            event_type="corporate",
            event_date=date(2024, 7, 15),
        )
        assert e.year == 2024

    def test_year_updates_on_date_change(self):
        from socialwarehouse.events.models import Event

        e = Event.objects.create(
            event_type="corporate",
            event_date=date(2024, 7, 15),
        )
        e.event_date = date(2025, 1, 1)
        e.save()
        e.refresh_from_db()
        assert e.year == 2025


@pytest.mark.django_db
class TestObligationLifecycle(TestCase):
    """Obligation balance tracking via apply_event."""

    def setUp(self):
        from socialwarehouse.transactions.models import Obligation

        self.obligation = Obligation.objects.create(
            obligation_type="loan",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            counterparty_uuid=generate_entity_uuid4(),
            counterparty_type="person",
            agent_uuid=generate_entity_uuid4(),
            agent_type="committee",
        )

    def test_repayment_reduces_balance(self):
        self.obligation.apply_event("repayment", Decimal("3000.00"))
        assert self.obligation.current_balance == Decimal("7000.00")
        assert self.obligation.status == "active"

    def test_full_repayment_sets_paid(self):
        self.obligation.apply_event("repayment", Decimal("10000.00"))
        assert self.obligation.current_balance == Decimal("0.00")
        assert self.obligation.status == "paid"

    def test_forgiveness_sets_forgiven(self):
        self.obligation.apply_event("forgiveness", Decimal("10000.00"))
        assert self.obligation.current_balance == Decimal("0.00")
        assert self.obligation.status == "forgiven"

    def test_drawdown_increases_balance(self):
        self.obligation.apply_event("drawdown", Decimal("5000.00"))
        assert self.obligation.current_balance == Decimal("15000.00")

    def test_overpayment_floors_at_zero(self):
        self.obligation.apply_event("repayment", Decimal("15000.00"))
        assert self.obligation.current_balance == Decimal("0.00")
        assert self.obligation.status == "paid"


@pytest.mark.django_db
class TestTransactionAutoType(TestCase):
    """Each transaction subclass auto-sets transaction_type on save."""

    def _make_tx_kwargs(self):
        return {
            "from_agent_uuid": generate_entity_uuid4(),
            "from_agent_type": "person",
            "to_agent_uuid": generate_entity_uuid4(),
            "to_agent_type": "committee",
            "amount": Decimal("100.00"),
            "transaction_date": date(2024, 6, 1),
        }

    def test_contribution_type(self):
        from socialwarehouse.transactions.models import Contribution

        c = Contribution.objects.create(**self._make_tx_kwargs())
        assert c.transaction_type == "contribution"

    def test_expenditure_type(self):
        from socialwarehouse.transactions.models import Expenditure

        e = Expenditure.objects.create(**self._make_tx_kwargs())
        assert e.transaction_type == "expenditure"

    def test_transfer_type(self):
        from socialwarehouse.transactions.models import Transfer

        t = Transfer.objects.create(**self._make_tx_kwargs())
        assert t.transaction_type == "transfer"
