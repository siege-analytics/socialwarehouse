import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.test import TestCase

from socialwarehouse.api.agents.serializers import (
    ClassificationSerializer,
    CommitteeSerializer,
    OrganizationSerializer,
    RoleSerializer,
)
from socialwarehouse.api.events.serializers import (
    EventListSerializer,
    EventSerializer,
)
from socialwarehouse.api.political.serializers import (
    ElectionSerializer,
    OfficeSerializer,
    OfficeTermSerializer,
)
from socialwarehouse.api.transactions.serializers import (
    ContributionSerializer,
    ObligationSerializer,
)


@pytest.mark.django_db
class TestAgentSerializers(TestCase):
    def test_committee_serializer_fields(self):
        from socialwarehouse.agents.models import Committee
        c = Committee.objects.create(
            name="Test PAC",
            committee_type="pac",
            data_source="fec",
            jurisdiction_state="TX",
        )
        s = CommitteeSerializer(c)
        assert s.data["name"] == "Test PAC"
        assert s.data["committee_type"] == "pac"
        assert "entity_uuid" in s.data

    def test_organization_serializer_fields(self):
        from socialwarehouse.agents.models import Organization
        o = Organization.objects.create(
            name="Acme Corp",
            organization_type="corporation",
            data_source="sec",
        )
        s = OrganizationSerializer(o)
        assert s.data["name"] == "Acme Corp"
        assert "entity_uuid" in s.data

    def test_classification_serializer_fields(self):
        from socialwarehouse.agents.models import Classification
        cl = Classification.objects.create(
            agent_uuid=uuid.uuid4(),
            agent_type="committee",
            classification_type="party_affiliation",
            classification_value="democratic",
            effective_from=date(2024, 1, 1),
            data_source="fec",
        )
        s = ClassificationSerializer(cl)
        assert s.data["classification_type"] == "party_affiliation"
        assert s.data["classification_value"] == "democratic"

    def test_role_serializer_fields(self):
        from socialwarehouse.agents.models import Role
        r = Role.objects.create(
            agent_uuid=uuid.uuid4(),
            agent_type="person",
            role_type="treasurer",
            role_context="committee",
            context_entity_uuid=uuid.uuid4(),
            context_entity_type="committee",
            effective_from=date(2024, 1, 1),
            data_source="fec",
        )
        s = RoleSerializer(r)
        assert s.data["role_type"] == "treasurer"


@pytest.mark.django_db
class TestPoliticalSerializers(TestCase):
    def test_office_serializer_fields(self):
        from socialwarehouse.political.models import Office
        o = Office.objects.create(
            name="US House TX-07",
            jurisdiction_level="federal",
            jurisdiction_state="TX",
            chamber="us_house",
            district_number="07",
        )
        s = OfficeSerializer(o)
        assert s.data["name"] == "US House TX-07"
        assert s.data["chamber"] == "us_house"

    def test_election_serializer_fields(self):
        from socialwarehouse.political.models import Election
        e = Election.objects.create(
            election_date=date(2024, 11, 5),
            election_type="general",
            jurisdiction_level="federal",
            jurisdiction_state="TX",
        )
        s = ElectionSerializer(e)
        assert s.data["election_type"] == "general"
        assert s.data["year"] == 2024

    def test_office_term_serializer_fields(self):
        from socialwarehouse.political.models import Office, OfficeTerm
        office = Office.objects.create(
            name="US House TX-07",
            jurisdiction_level="federal",
            jurisdiction_state="TX",
            chamber="us_house",
        )
        term = OfficeTerm.objects.create(
            office=office,
            person_uuid=uuid.uuid4(),
            start_date=date(2023, 1, 3),
            term_type="full",
            data_source="congress",
        )
        s = OfficeTermSerializer(term)
        assert s.data["office_name"] == "US House TX-07"
        assert s.data["term_type"] == "full"


@pytest.mark.django_db
class TestTransactionSerializers(TestCase):
    def test_contribution_serializer_fields(self):
        from socialwarehouse.transactions.models import Contribution
        c = Contribution.objects.create(
            from_agent_uuid=uuid.uuid4(),
            from_agent_type="person",
            to_agent_uuid=uuid.uuid4(),
            to_agent_type="committee",
            amount=Decimal("500.00"),
            transaction_date=date(2024, 3, 15),
            data_source="fec",
            jurisdiction_state="TX",
        )
        s = ContributionSerializer(c)
        assert s.data["transaction_type"] == "contribution"
        assert s.data["amount"] == "500.00"

    def test_obligation_serializer_fields(self):
        from socialwarehouse.transactions.models import Obligation
        o = Obligation.objects.create(
            obligation_type="loan_received",
            original_amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            status="outstanding",
            agent_uuid=uuid.uuid4(),
            agent_type="committee",
            counterparty_uuid=uuid.uuid4(),
            counterparty_type="person",
            data_source="fec",
        )
        s = ObligationSerializer(o)
        assert s.data["obligation_type"] == "loan_received"
        assert s.data["status"] == "outstanding"


@pytest.mark.django_db
class TestEventSerializers(TestCase):
    def test_event_list_serializer(self):
        from socialwarehouse.events.models import Event, EventParticipant
        e = Event.objects.create(
            event_type="electoral",
            event_date=date(2024, 11, 5),
            jurisdiction_state="TX",
        )
        EventParticipant.objects.create(
            event=e,
            agent_uuid=uuid.uuid4(),
            agent_type="person",
            role_in_event="candidate",
        )
        from django.db.models import Count
        e_annotated = Event.objects.annotate(
            participant_count=Count("participants")
        ).get(pk=e.pk)
        s = EventListSerializer(e_annotated)
        assert s.data["event_type"] == "electoral"
        assert s.data["participant_count"] == 1

    def test_event_detail_serializer_with_participants(self):
        from socialwarehouse.events.models import Event, EventParticipant
        e = Event.objects.create(
            event_type="transaction",
            event_date=date(2024, 3, 15),
        )
        EventParticipant.objects.create(
            event=e,
            agent_uuid=uuid.uuid4(),
            agent_type="person",
            role_in_event="source",
        )
        e = Event.objects.prefetch_related("participants").get(pk=e.pk)
        s = EventSerializer(e)
        assert len(s.data["participants"]) == 1
        assert s.data["participants"][0]["role_in_event"] == "source"

    def test_event_detail_with_electoral_detail(self):
        from socialwarehouse.events.models import ElectoralEvent, Event
        e = Event.objects.create(
            event_type="electoral",
            event_date=date(2024, 11, 20),
        )
        ElectoralEvent.objects.create(
            event=e,
            electoral_event_type="certification",
            is_certified=True,
        )
        e = Event.objects.prefetch_related("electoral_detail").get(pk=e.pk)
        s = EventSerializer(e)
        assert s.data["electoral_detail"]["is_certified"] is True


@pytest.mark.django_db
class TestURLRegistration(TestCase):
    def test_url_patterns_resolve(self):
        from django.urls import reverse
        assert reverse("agents:person-list")
        assert reverse("agents:committee-list")
        assert reverse("agents:organization-list")
        assert reverse("agents:classification-list")
        assert reverse("agents:role-list")
        assert reverse("political:office-list")
        assert reverse("political:seat-list")
        assert reverse("political:election-list")
        assert reverse("political:contest-list")
        assert reverse("political:term-list")
        assert reverse("transactions:contribution-list")
        assert reverse("transactions:expenditure-list")
        assert reverse("transactions:transfer-list")
        assert reverse("transactions:obligation-list")
        assert reverse("events:event-list")
