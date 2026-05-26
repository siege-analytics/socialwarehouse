import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.test import TestCase

from socialwarehouse.transactions.models import (
    Contribution,
    Expenditure,
    Obligation,
    ObligationEvent,
    Transfer,
    TransactionGroup,
)


def _agent():
    return uuid.uuid4()


@pytest.mark.django_db
class TestContribution(TestCase):
    def test_create_contribution(self):
        c = Contribution.objects.create(
            from_agent_uuid=_agent(),
            from_agent_type="person",
            to_agent_uuid=_agent(),
            to_agent_type="committee",
            amount=Decimal("2700.00"),
            transaction_date=date(2024, 3, 15),
            data_source="fec",
            jurisdiction_level="federal",
            jurisdiction_state="TX",
        )
        assert c.transaction_type == "contribution"
        assert c.transaction_uuid is not None
        assert c.amount == Decimal("2700.00")

    def test_contribution_str(self):
        c = Contribution(
            from_agent_uuid=_agent(),
            to_agent_uuid=_agent(),
            amount=Decimal("500.00"),
            transaction_date=date(2024, 1, 1),
            transaction_type="contribution",
        )
        s = str(c)
        assert "$500.00" in s
        assert "contribution" in s

    def test_query_contributions_by_state_and_date(self):
        to_committee = _agent()
        Contribution.objects.create(
            from_agent_uuid=_agent(), from_agent_type="person",
            to_agent_uuid=to_committee, to_agent_type="committee",
            amount=Decimal("1000.00"), transaction_date=date(2024, 1, 15),
            jurisdiction_state="TX",
        )
        Contribution.objects.create(
            from_agent_uuid=_agent(), from_agent_type="person",
            to_agent_uuid=to_committee, to_agent_type="committee",
            amount=Decimal("2000.00"), transaction_date=date(2024, 6, 15),
            jurisdiction_state="TX",
        )
        Contribution.objects.create(
            from_agent_uuid=_agent(), from_agent_type="person",
            to_agent_uuid=_agent(), to_agent_type="committee",
            amount=Decimal("500.00"), transaction_date=date(2024, 3, 1),
            jurisdiction_state="CA",
        )
        tx_2024 = Contribution.objects.filter(
            jurisdiction_state="TX",
            transaction_date__year=2024,
        )
        assert tx_2024.count() == 2
        total = sum(c.amount for c in tx_2024)
        assert total == Decimal("3000.00")


@pytest.mark.django_db
class TestExpenditure(TestCase):
    def test_create_expenditure(self):
        e = Expenditure.objects.create(
            from_agent_uuid=_agent(),
            from_agent_type="committee",
            to_agent_uuid=_agent(),
            to_agent_type="organization",
            amount=Decimal("5000.00"),
            transaction_date=date(2024, 4, 1),
            data_source="fec",
        )
        assert e.transaction_type == "expenditure"

    def test_expenditure_with_description(self):
        e = Expenditure.objects.create(
            from_agent_uuid=_agent(),
            from_agent_type="committee",
            to_agent_uuid=_agent(),
            to_agent_type="organization",
            amount=Decimal("15000.00"),
            transaction_date=date(2024, 9, 1),
            description="Television advertising buy",
        )
        assert e.description == "Television advertising buy"


@pytest.mark.django_db
class TestTransfer(TestCase):
    def test_create_transfer(self):
        t = Transfer.objects.create(
            from_agent_uuid=_agent(),
            from_agent_type="committee",
            to_agent_uuid=_agent(),
            to_agent_type="committee",
            amount=Decimal("10000.00"),
            transaction_date=date(2024, 5, 1),
            data_source="fec",
        )
        assert t.transaction_type == "transfer"

    def test_pac_to_pac_transfer(self):
        pac_a = _agent()
        pac_b = _agent()
        Transfer.objects.create(
            from_agent_uuid=pac_a, from_agent_type="committee",
            to_agent_uuid=pac_b, to_agent_type="committee",
            amount=Decimal("25000.00"),
            transaction_date=date(2024, 7, 1),
        )
        qs = Transfer.objects.filter(from_agent_uuid=pac_a)
        assert qs.count() == 1
        assert qs.first().to_agent_uuid == pac_b


@pytest.mark.django_db
class TestObligation(TestCase):
    def setUp(self):
        self.committee = _agent()
        self.lender = _agent()
        self.loan = Obligation.objects.create(
            obligation_type="loan",
            original_amount=Decimal("50000.00"),
            current_balance=Decimal("50000.00"),
            status="active",
            agent_uuid=self.committee,
            agent_type="committee",
            counterparty_uuid=self.lender,
            counterparty_type="person",
            data_source="fec",
        )

    def test_create_loan(self):
        assert self.loan.obligation_uuid is not None
        assert self.loan.status == "active"
        assert self.loan.current_balance == Decimal("50000.00")

    def test_partial_repayment(self):
        self.loan.apply_event("repayment", Decimal("20000.00"))
        self.loan.save()
        assert self.loan.current_balance == Decimal("30000.00")
        assert self.loan.status == "active"

    def test_full_repayment_marks_paid(self):
        self.loan.apply_event("repayment", Decimal("50000.00"))
        self.loan.save()
        assert self.loan.current_balance == Decimal("0.00")
        assert self.loan.status == "paid"

    def test_forgiveness_marks_forgiven(self):
        self.loan.apply_event("forgiveness", Decimal("50000.00"))
        self.loan.save()
        assert self.loan.current_balance == Decimal("0.00")
        assert self.loan.status == "forgiven"

    def test_drawdown_increases_balance(self):
        self.loan.apply_event("drawdown", Decimal("10000.00"))
        self.loan.save()
        assert self.loan.current_balance == Decimal("60000.00")
        assert self.loan.status == "active"

    def test_balance_never_goes_negative(self):
        self.loan.apply_event("repayment", Decimal("99999.00"))
        self.loan.save()
        assert self.loan.current_balance == Decimal("0.00")

    def test_str(self):
        s = str(self.loan)
        assert "loan" in s
        assert "50000.00" in s
        assert "active" in s


@pytest.mark.django_db
class TestObligationEvent(TestCase):
    def test_create_obligation_event(self):
        loan = Obligation.objects.create(
            obligation_type="loan",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            agent_uuid=_agent(), agent_type="committee",
            counterparty_uuid=_agent(), counterparty_type="person",
        )
        oe = ObligationEvent.objects.create(
            obligation=loan,
            obligation_event_type="repayment",
            from_agent_uuid=loan.agent_uuid,
            from_agent_type="committee",
            to_agent_uuid=loan.counterparty_uuid,
            to_agent_type="person",
            amount=Decimal("5000.00"),
            transaction_date=date(2024, 6, 1),
        )
        assert oe.transaction_type == "obligation_event"
        assert oe.obligation == loan

    def test_multiple_events_on_obligation(self):
        loan = Obligation.objects.create(
            obligation_type="loan",
            original_amount=Decimal("30000.00"),
            current_balance=Decimal("30000.00"),
            agent_uuid=_agent(), agent_type="committee",
            counterparty_uuid=_agent(), counterparty_type="person",
        )
        for i in range(3):
            ObligationEvent.objects.create(
                obligation=loan,
                obligation_event_type="repayment",
                from_agent_uuid=loan.agent_uuid,
                from_agent_type="committee",
                to_agent_uuid=loan.counterparty_uuid,
                to_agent_type="person",
                amount=Decimal("10000.00"),
                transaction_date=date(2024, 1 + i, 1),
            )
        assert loan.events.count() == 3


@pytest.mark.django_db
class TestTransactionGroup(TestCase):
    def test_create_group(self):
        group = TransactionGroup.objects.create(
            group_type="jfc_distribution",
            description="JFC distributes to 5 committees",
        )
        assert group.group_uuid is not None

    def test_jfc_distribution_multi_leg(self):
        """JFC receives $100K, distributes to 3 committees."""
        jfc = _agent()
        donor = _agent()
        c = Contribution.objects.create(
            from_agent_uuid=donor, from_agent_type="person",
            to_agent_uuid=jfc, to_agent_type="committee",
            amount=Decimal("100000.00"),
            transaction_date=date(2024, 1, 1),
        )
        transfers = []
        for _ in range(3):
            t = Transfer.objects.create(
                from_agent_uuid=jfc, from_agent_type="committee",
                to_agent_uuid=_agent(), to_agent_type="committee",
                amount=Decimal("33333.33"),
                transaction_date=date(2024, 1, 2),
            )
            transfers.append(t)
        group = TransactionGroup.objects.create(
            group_type="jfc_distribution",
            description="JFC splits $100K to 3 committees",
        )
        group.contributions.add(c)
        group.transfers.add(*transfers)
        assert group.contributions.count() == 1
        assert group.transfers.count() == 3

    def test_group_str(self):
        group = TransactionGroup(
            group_type="bundled_contribution",
            description="Bundled from event",
        )
        s = str(group)
        assert "bundled_contribution" in s
