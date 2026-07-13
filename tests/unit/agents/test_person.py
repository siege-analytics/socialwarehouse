import pytest
from django.test import TestCase

from socialwarehouse.agents.models import Committee, Organization, Person
from socialwarehouse.core.agent import Agent
from socialwarehouse.core.mixins import generate_entity_uuid5


@pytest.mark.django_db
class TestPersonModel(TestCase):
    def test_create_person(self):
        p = Person.objects.create(
            entity_uuid=generate_entity_uuid5("vendor", "P100"),
            full_name="Maria Q. Public",
            given_name="Maria",
            family_name="Public",
            middle_name="Q",
            data_source="vendor",
            source_record_id="P100",
            birth_year=1980,
        )
        assert p.pk is not None
        assert str(p) == "Maria Q. Public"
        assert p.family_name == "Public"
        assert p.birth_year == 1980

    def test_person_starts_unlinked(self):
        p = Person.objects.create(
            entity_uuid=generate_entity_uuid5("vendor", "P101"),
            full_name="Unlinked Person",
            data_source="vendor",
            source_record_id="P101",
        )
        assert p.agent is None

    def test_link_agent_sets_reverse_accessor(self):
        agent = Agent.objects.create(subtype="person", data_source="vendor", source_record_id="P102")
        p = Person.objects.create(
            entity_uuid=generate_entity_uuid5("vendor", "P102"),
            full_name="Linked Person",
            data_source="vendor",
            source_record_id="P102",
        )
        returned = p.link_agent(agent)
        assert returned == agent
        p.refresh_from_db()
        assert p.agent == agent
        # Reverse one-to-one accessor on Agent is the lowercased class name.
        assert agent.person == p


@pytest.mark.django_db
class TestCommitteeOrganizationAgentLink(TestCase):
    def test_committee_gains_agent_link(self):
        agent = Agent.objects.create(subtype="committee", data_source="fec", source_record_id="C500")
        c = Committee.objects.create(
            entity_uuid=generate_entity_uuid5("fec", "C500"),
            name="Linked PAC",
            committee_type="pac",
            source_system_id="C500",
            data_source="fec",
        )
        c.link_agent(agent)
        c.refresh_from_db()
        assert c.agent == agent
        assert agent.committee == c

    def test_organization_agent_link_nullable_by_default(self):
        o = Organization.objects.create(
            entity_uuid=generate_entity_uuid5("acme", "tx", "naics"),
            name="Acme Corp",
            data_source="fec",
        )
        # Backward-compatible: existing rows need no agent.
        assert o.agent is None
