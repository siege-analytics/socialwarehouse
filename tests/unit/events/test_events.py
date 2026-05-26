import uuid
from datetime import date

import pytest
from django.test import TestCase

from socialwarehouse.events.models import (
    CorporateEvent,
    ElectoralEvent,
    Event,
    EventParticipant,
    SpatioTemporalEvent,
)


@pytest.mark.django_db
class TestEvent(TestCase):
    def test_create_event(self):
        e = Event.objects.create(
            event_type="transaction",
            event_date=date(2024, 3, 15),
            jurisdiction_state="TX",
            data_source="fec",
        )
        assert e.event_uuid is not None
        assert e.year == 2024

    def test_year_auto_derived(self):
        e = Event(event_type="corporate", event_date=date(2023, 7, 1))
        e.save()
        assert e.year == 2023

    def test_str(self):
        e = Event(event_type="electoral", event_date=date(2024, 11, 5))
        assert "electoral" in str(e)
        assert "2024-11-05" in str(e)


@pytest.mark.django_db
class TestEventParticipant(TestCase):
    def test_add_participant(self):
        e = Event.objects.create(
            event_type="transaction",
            event_date=date(2024, 3, 15),
        )
        agent = uuid.uuid4()
        p = EventParticipant.objects.create(
            event=e,
            agent_uuid=agent,
            agent_type="person",
            role_in_event="source",
        )
        assert p.agent_uuid == agent
        assert p.role_in_event == "source"

    def test_unique_event_agent_role(self):
        e = Event.objects.create(
            event_type="transaction",
            event_date=date(2024, 1, 1),
        )
        agent = uuid.uuid4()
        EventParticipant.objects.create(
            event=e, agent_uuid=agent, agent_type="person", role_in_event="source",
        )
        with pytest.raises(Exception):
            EventParticipant.objects.create(
                event=e, agent_uuid=agent, agent_type="person", role_in_event="source",
            )

    def test_same_agent_different_roles(self):
        e = Event.objects.create(
            event_type="electoral",
            event_date=date(2024, 11, 5),
        )
        agent = uuid.uuid4()
        EventParticipant.objects.create(
            event=e, agent_uuid=agent, agent_type="person", role_in_event="candidate",
        )
        EventParticipant.objects.create(
            event=e, agent_uuid=agent, agent_type="person", role_in_event="winner",
        )
        assert e.participants.count() == 2


@pytest.mark.django_db
class TestSharedQuerySurface(TestCase):
    def setUp(self):
        self.person = uuid.uuid4()
        self.org = uuid.uuid4()

        self.e_transaction = Event.objects.create(
            event_type="transaction", event_date=date(2024, 3, 15),
            jurisdiction_state="TX",
        )
        EventParticipant.objects.create(
            event=self.e_transaction, agent_uuid=self.person,
            agent_type="person", role_in_event="source",
        )

        self.e_corporate = Event.objects.create(
            event_type="corporate", event_date=date(2024, 6, 1),
            jurisdiction_state="TX",
        )
        EventParticipant.objects.create(
            event=self.e_corporate, agent_uuid=self.org,
            agent_type="organization", role_in_event="predecessor",
        )

        self.e_electoral = Event.objects.create(
            event_type="electoral", event_date=date(2024, 11, 5),
            jurisdiction_state="TX",
        )
        EventParticipant.objects.create(
            event=self.e_electoral, agent_uuid=self.person,
            agent_type="person", role_in_event="winner",
        )

    def test_all_events_for_person(self):
        events = Event.objects.filter(
            participants__agent_uuid=self.person,
        ).distinct()
        assert events.count() == 2

    def test_all_events_for_org(self):
        events = Event.objects.filter(
            participants__agent_uuid=self.org,
        ).distinct()
        assert events.count() == 1

    def test_filter_by_event_type(self):
        events = Event.objects.filter(
            participants__agent_uuid=self.person,
            event_type="electoral",
        ).distinct()
        assert events.count() == 1

    def test_filter_by_jurisdiction_and_date(self):
        events = Event.objects.filter(
            jurisdiction_state="TX",
            event_date__year=2024,
        )
        assert events.count() == 3

    def test_filter_by_role(self):
        winners = EventParticipant.objects.filter(
            role_in_event="winner",
        )
        assert winners.count() == 1
        assert winners.first().agent_uuid == self.person


@pytest.mark.django_db
class TestCorporateEvent(TestCase):
    def test_create_merger(self):
        e = Event.objects.create(
            event_type="corporate", event_date=date(2024, 3, 1),
            data_source="sec",
        )
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        ce = CorporateEvent.objects.create(
            event=e,
            corporate_event_type="merger",
            predecessor_uuid=org_a,
            successor_uuid=org_b,
        )
        assert ce.corporate_event_type == "merger"
        assert ce.predecessor_uuid == org_a

    def test_corporate_event_with_succession_link(self):
        e = Event.objects.create(
            event_type="corporate", event_date=date(2024, 1, 1),
        )
        rel_uuid = uuid.uuid4()
        ce = CorporateEvent.objects.create(
            event=e,
            corporate_event_type="spinoff",
            relationship_uuid=rel_uuid,
        )
        assert ce.relationship_uuid == rel_uuid

    def test_access_via_event(self):
        e = Event.objects.create(
            event_type="corporate", event_date=date(2024, 6, 1),
        )
        CorporateEvent.objects.create(
            event=e, corporate_event_type="dissolution",
        )
        assert e.corporate_detail.corporate_event_type == "dissolution"


@pytest.mark.django_db
class TestSpatioTemporalEvent(TestCase):
    def test_create_redistricting(self):
        e = Event.objects.create(
            event_type="spatiotemporal", event_date=date(2023, 6, 15),
            jurisdiction_state="TX",
        )
        ste = SpatioTemporalEvent.objects.create(
            event=e,
            spatiotemporal_event_type="redistricting_enacted",
            redistricting_plan_id="2020_enacted",
            affected_boundary_type="congressional_district",
            affected_jurisdiction_state="TX",
        )
        assert ste.redistricting_plan_id == "2020_enacted"

    def test_annexation_event(self):
        e = Event.objects.create(
            event_type="spatiotemporal", event_date=date(2024, 1, 1),
        )
        ste = SpatioTemporalEvent.objects.create(
            event=e,
            spatiotemporal_event_type="annexation",
            affected_jurisdiction_state="TX",
        )
        assert ste.spatiotemporal_event_type == "annexation"


@pytest.mark.django_db
class TestElectoralEvent(TestCase):
    def test_create_certification(self):
        e = Event.objects.create(
            event_type="electoral", event_date=date(2024, 11, 20),
            jurisdiction_state="TX",
        )
        contest = uuid.uuid4()
        ee = ElectoralEvent.objects.create(
            event=e,
            electoral_event_type="certification",
            contest_uuid=contest,
            is_certified=True,
        )
        assert ee.is_certified is True
        assert ee.contest_uuid == contest

    def test_recount_event(self):
        e = Event.objects.create(
            event_type="electoral", event_date=date(2024, 12, 1),
        )
        ee = ElectoralEvent.objects.create(
            event=e,
            electoral_event_type="recount",
            is_recount=True,
        )
        assert ee.is_recount is True
        assert ee.is_certified is False

    def test_str_certified(self):
        e = Event.objects.create(
            event_type="electoral", event_date=date(2024, 11, 20),
        )
        ee = ElectoralEvent(
            event=e,
            electoral_event_type="certification",
            is_certified=True,
        )
        s = str(ee)
        assert "certification" in s
        assert "certified" in s
