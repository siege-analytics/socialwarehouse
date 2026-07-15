import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.test import TestCase

from socialwarehouse.agents.models import Committee, Organization, Person
from socialwarehouse.core.agent import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_DISSOLVED,
    Agent,
)
from socialwarehouse.core.mixins import generate_entity_uuid5


@pytest.mark.django_db
class TestAgentSupertype(TestCase):
    def test_create_agent_each_subtype(self):
        for subtype in ("person", "committee", "organization"):
            a = Agent.objects.create(subtype=subtype, data_source="fec", source_record_id=f"X{subtype}")
            assert a.pk is not None
            assert a.subtype == subtype
            assert a.lifecycle_state == LIFECYCLE_ACTIVE
            assert a.is_active is True

    def test_entity_uuid_autoassigned_uuid5_deterministic(self):
        a = Agent.objects.create(subtype="committee", data_source="fec", source_record_id="C00123456")
        expected = generate_entity_uuid5("committee", "fec", "C00123456")
        assert a.entity_uuid == expected
        # Recompute via the helper exposed for pre-row wiring.
        assert Agent.make_entity_uuid("committee", "fec", "C00123456") == expected

    def test_entity_uuid_not_overwritten_when_supplied(self):
        eu = uuid.uuid4()
        a = Agent.objects.create(
            entity_uuid=eu, subtype="person", data_source="vendor", source_record_id="P1"
        )
        a.refresh_from_db()
        assert a.entity_uuid == eu

    def test_lifecycle_transition_to_dissolved(self):
        a = Agent.objects.create(subtype="committee", data_source="fec", source_record_id="C1")
        a.lifecycle_state = LIFECYCLE_DISSOLVED
        a.dissolved_on = date(2021, 6, 1)
        a.save(update_fields=["lifecycle_state", "dissolved_on"])
        a.refresh_from_db()
        assert a.is_active is False
        assert a.dissolved_on == date(2021, 6, 1)

    def test_resolution_confidence_semantics(self):
        a = Agent.objects.create(
            subtype="person",
            data_source="vendor",
            source_record_id="P2",
            resolution_confidence=Decimal("0.9750"),
        )
        a.refresh_from_db()
        assert a.resolution_confidence == Decimal("0.9750")
        # NULL when not scored.
        b = Agent.objects.create(subtype="person", data_source="vendor", source_record_id="P3")
        assert b.resolution_confidence is None

    def test_resolution_confidence_range_enforced(self):
        # The [0, 1] range is DB-enforced (ck_agent_resolution_confidence_0_1),
        # not just documented. Out-of-range scores must be rejected.
        for bad in (Decimal("1.5"), Decimal("-0.1")):
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Agent.objects.create(
                        subtype="person",
                        data_source="vendor",
                        source_record_id=f"bad{bad}",
                        resolution_confidence=bad,
                    )
        # Boundaries and NULL are accepted.
        for ok in (Decimal("0"), Decimal("1"), Decimal("0.5000"), None):
            a = Agent.objects.create(
                subtype="person",
                data_source="vendor",
                source_record_id=f"ok{ok}",
                resolution_confidence=ok,
            )
            assert a.resolution_confidence == ok

    def test_polymorphic_dispatch_resolves_concrete_subtype(self):
        # Committee subtype -> agent.committee reverse accessor.
        agent_c = Agent.objects.create(subtype="committee", data_source="fec", source_record_id="C2")
        committee = Committee.objects.create(
            entity_uuid=generate_entity_uuid5("fec", "C2"),
            name="Test PAC",
            committee_type="pac",
            source_system_id="C2",
            data_source="fec",
            agent=agent_c,
        )
        resolved = agent_c.get_subtype_instance()
        assert resolved == committee

        # Organization subtype -> agent.organization.
        agent_o = Agent.objects.create(subtype="organization", data_source="fec", source_record_id="O1")
        org = Organization.objects.create(
            entity_uuid=generate_entity_uuid5("acme", "tx", "naics"),
            name="Acme Corp",
            data_source="fec",
            agent=agent_o,
        )
        assert agent_o.get_subtype_instance() == org

        # Person subtype -> agent.person.
        agent_p = Agent.objects.create(subtype="person", data_source="vendor", source_record_id="P4")
        person = Person.objects.create(
            entity_uuid=generate_entity_uuid5("vendor", "P4"),
            full_name="Jane Doe",
            data_source="vendor",
            agent=agent_p,
        )
        assert agent_p.get_subtype_instance() == person

    def test_dispatch_returns_none_when_detail_not_linked(self):
        agent_p = Agent.objects.create(subtype="person", data_source="vendor", source_record_id="P5")
        # No Person detail row links to this agent yet.
        assert agent_p.get_subtype_instance() is None

    def test_str(self):
        a = Agent.objects.create(subtype="committee", data_source="fec", source_record_id="C3")
        assert "committee" in str(a)
        assert "active" in str(a)
