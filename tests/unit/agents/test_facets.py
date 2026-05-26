import uuid
from datetime import date

import pytest
from django.test import TestCase

from socialwarehouse.agents.models import (
    Classification,
    RelationshipControl,
    RelationshipCorporateSuccession,
    RelationshipDAFConduit,
    RelationshipSimple,
    RelationshipSponsor,
    RelationshipSubsidiary,
    Role,
)
from socialwarehouse.core.mixins import generate_entity_uuid4


@pytest.mark.django_db
class TestClassification(TestCase):
    def setUp(self):
        self.agent_uuid = uuid.uuid4()

    def test_create_classification(self):
        c = Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="organization",
            classification_type="tax_status",
            value="501(c)(3)",
            data_source="irs",
            jurisdiction_level="federal",
        )
        assert c.classification_uuid is not None
        assert c.value == "501(c)(3)"
        assert c.is_current is True

    def test_multiple_concurrent_classifications(self):
        Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="organization",
            classification_type="tax_status",
            value="501(c)(4)",
            data_source="irs",
        )
        Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="organization",
            classification_type="partisan_alignment",
            value="nonpartisan",
            data_source="manual",
        )
        qs = Classification.objects.filter(agent_uuid=self.agent_uuid)
        assert qs.count() == 2

    def test_temporal_classification_supersession(self):
        Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="committee",
            classification_type="committee_subtype",
            value="super_pac",
            effective_from=date(2020, 1, 1),
            effective_to=date(2022, 12, 31),
            data_source="fec",
        )
        Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="committee",
            classification_type="committee_subtype",
            value="hybrid_pac",
            effective_from=date(2023, 1, 1),
            data_source="fec",
        )
        current = Classification.objects.filter(
            agent_uuid=self.agent_uuid,
            classification_type="committee_subtype",
            effective_to__isnull=True,
        )
        assert current.count() == 1
        assert current.first().value == "hybrid_pac"

    def test_classification_uuid_unique(self):
        c1 = Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="person",
            classification_type="voter_category",
            value="super_voter",
        )
        c2 = Classification.objects.create(
            agent_uuid=self.agent_uuid,
            agent_type="person",
            classification_type="voter_category",
            value="low_propensity",
        )
        assert c1.classification_uuid != c2.classification_uuid

    def test_str(self):
        c = Classification(
            agent_uuid=self.agent_uuid,
            agent_type="organization",
            classification_type="tax_status",
            value="501(c)(3)",
        )
        s = str(c)
        assert "tax_status" in s
        assert "501(c)(3)" in s


@pytest.mark.django_db
class TestRole(TestCase):
    def setUp(self):
        self.person_uuid = uuid.uuid4()
        self.committee_uuid = uuid.uuid4()

    def test_create_role(self):
        r = Role.objects.create(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=self.committee_uuid,
            counterparty_type="committee",
            data_source="fec",
        )
        assert r.role_uuid is not None
        assert r.role_type == "treasurer"
        assert r.is_current is True

    def test_temporal_role_transfer(self):
        """Person is treasurer of Committee A, then transfers to Committee B."""
        committee_b = uuid.uuid4()
        Role.objects.create(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=self.committee_uuid,
            counterparty_type="committee",
            effective_from=date(2020, 1, 1),
            effective_to=date(2022, 12, 31),
            data_source="fec",
        )
        Role.objects.create(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=committee_b,
            counterparty_type="committee",
            effective_from=date(2023, 1, 1),
            data_source="fec",
        )
        current_roles = Role.objects.filter(
            agent_uuid=self.person_uuid,
            role_type="treasurer",
            effective_to__isnull=True,
        )
        assert current_roles.count() == 1
        assert current_roles.first().counterparty_uuid == committee_b

    def test_multiple_concurrent_roles(self):
        """Person can be both treasurer and candidate simultaneously."""
        Role.objects.create(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=self.committee_uuid,
            counterparty_type="committee",
        )
        Role.objects.create(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="candidate",
            counterparty_uuid=self.committee_uuid,
            counterparty_type="committee",
        )
        qs = Role.objects.filter(agent_uuid=self.person_uuid)
        assert qs.count() == 2

    def test_role_without_counterparty(self):
        r = Role.objects.create(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="lobbyist",
        )
        assert r.counterparty_uuid is None
        assert r.counterparty_type == ""

    def test_query_who_was_treasurer_on_date(self):
        """Temporal query: who was treasurer of Committee X on 2021-06-15?"""
        person_a = uuid.uuid4()
        person_b = uuid.uuid4()
        Role.objects.create(
            agent_uuid=person_a,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=self.committee_uuid,
            counterparty_type="committee",
            effective_from=date(2020, 1, 1),
            effective_to=date(2021, 3, 31),
        )
        Role.objects.create(
            agent_uuid=person_b,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=self.committee_uuid,
            counterparty_type="committee",
            effective_from=date(2021, 4, 1),
        )
        query_date = date(2021, 6, 15)
        treasurers = Role.objects.filter(
            counterparty_uuid=self.committee_uuid,
            role_type="treasurer",
            effective_from__lte=query_date,
        ).exclude(
            effective_to__isnull=False,
            effective_to__lt=query_date,
        )
        assert treasurers.count() == 1
        assert treasurers.first().agent_uuid == person_b

    def test_str_with_counterparty(self):
        r = Role(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="treasurer",
            counterparty_uuid=self.committee_uuid,
        )
        s = str(r)
        assert "treasurer" in s
        assert str(self.committee_uuid) in s

    def test_str_without_counterparty(self):
        r = Role(
            agent_uuid=self.person_uuid,
            agent_type="person",
            role_type="lobbyist",
        )
        s = str(r)
        assert "lobbyist" in s
        assert "->" not in s


@pytest.mark.django_db
class TestRelationshipSimple(TestCase):
    def test_create_spouse_relationship(self):
        a = uuid.uuid4()
        b = uuid.uuid4()
        r = RelationshipSimple.objects.create(
            from_agent_uuid=a,
            from_agent_type="person",
            to_agent_uuid=b,
            to_agent_type="person",
            relationship_type="spouse_of",
        )
        assert r.relationship_uuid is not None
        assert r.is_current is True

    def test_employer_employee(self):
        person = uuid.uuid4()
        org = uuid.uuid4()
        RelationshipSimple.objects.create(
            from_agent_uuid=org,
            from_agent_type="organization",
            to_agent_uuid=person,
            to_agent_type="person",
            relationship_type="employer_of",
        )
        qs = RelationshipSimple.objects.filter(
            to_agent_uuid=person,
            relationship_type="employer_of",
        )
        assert qs.count() == 1
        assert qs.first().from_agent_uuid == org

    def test_temporal_affiliation(self):
        a = uuid.uuid4()
        b = uuid.uuid4()
        RelationshipSimple.objects.create(
            from_agent_uuid=a,
            from_agent_type="person",
            to_agent_uuid=b,
            to_agent_type="organization",
            relationship_type="affiliated_with",
            effective_from=date(2019, 1, 1),
            effective_to=date(2021, 12, 31),
        )
        rel = RelationshipSimple.objects.get(from_agent_uuid=a)
        assert rel.is_current is False


@pytest.mark.django_db
class TestRelationshipSponsor(TestCase):
    def test_create_sponsor_relationship(self):
        org = uuid.uuid4()
        committee = uuid.uuid4()
        r = RelationshipSponsor.objects.create(
            sponsor_uuid=org,
            sponsored_uuid=committee,
            data_source="fec",
        )
        assert r.relationship_uuid is not None
        assert r.sponsor_uuid == org
        assert r.sponsored_uuid == committee

    def test_query_committees_sponsored_by_org(self):
        org = uuid.uuid4()
        c1 = uuid.uuid4()
        c2 = uuid.uuid4()
        RelationshipSponsor.objects.create(sponsor_uuid=org, sponsored_uuid=c1)
        RelationshipSponsor.objects.create(sponsor_uuid=org, sponsored_uuid=c2)
        sponsored = RelationshipSponsor.objects.filter(sponsor_uuid=org)
        assert sponsored.count() == 2


@pytest.mark.django_db
class TestRelationshipControl(TestCase):
    def test_create_control_relationship(self):
        controller = uuid.uuid4()
        controlled = uuid.uuid4()
        r = RelationshipControl.objects.create(
            controller_uuid=controller,
            controller_type="person",
            controlled_uuid=controlled,
            controlled_type="committee",
            control_type="controls",
        )
        assert r.relationship_uuid is not None
        assert r.control_type == "controls"

    def test_default_control_type(self):
        r = RelationshipControl.objects.create(
            controller_uuid=uuid.uuid4(),
            controller_type="organization",
            controlled_uuid=uuid.uuid4(),
            controlled_type="committee",
        )
        assert r.control_type == "controls"


@pytest.mark.django_db
class TestRelationshipSubsidiary(TestCase):
    def test_create_subsidiary(self):
        parent = uuid.uuid4()
        child = uuid.uuid4()
        r = RelationshipSubsidiary.objects.create(
            parent_uuid=parent,
            child_uuid=child,
            data_source="sec",
        )
        assert r.relationship_uuid is not None

    def test_query_subsidiaries(self):
        parent = uuid.uuid4()
        children = [uuid.uuid4() for _ in range(3)]
        for c in children:
            RelationshipSubsidiary.objects.create(parent_uuid=parent, child_uuid=c)
        subs = RelationshipSubsidiary.objects.filter(parent_uuid=parent)
        assert subs.count() == 3


@pytest.mark.django_db
class TestRelationshipCorporateSuccession(TestCase):
    def test_create_merger(self):
        pred = uuid.uuid4()
        succ = uuid.uuid4()
        r = RelationshipCorporateSuccession.objects.create(
            predecessor_uuid=pred,
            successor_uuid=succ,
            succession_type="merger",
            succession_date=date(2023, 7, 1),
        )
        assert r.relationship_uuid is not None
        assert r.succession_type == "merger"
        assert r.succession_date == date(2023, 7, 1)

    def test_rename_continuation(self):
        org = uuid.uuid4()
        new_org = uuid.uuid4()
        r = RelationshipCorporateSuccession.objects.create(
            predecessor_uuid=org,
            successor_uuid=new_org,
            succession_type="rename",
        )
        assert r.succession_type == "rename"
        assert r.succession_date is None

    def test_query_successor_chain(self):
        a = uuid.uuid4()
        b = uuid.uuid4()
        c = uuid.uuid4()
        RelationshipCorporateSuccession.objects.create(
            predecessor_uuid=a, successor_uuid=b, succession_type="merger",
        )
        RelationshipCorporateSuccession.objects.create(
            predecessor_uuid=b, successor_uuid=c, succession_type="rename",
        )
        successors_of_a = RelationshipCorporateSuccession.objects.filter(
            predecessor_uuid=a,
        )
        assert successors_of_a.count() == 1
        assert successors_of_a.first().successor_uuid == b


@pytest.mark.django_db
class TestRelationshipDAFConduit(TestCase):
    def test_create_daf_conduit(self):
        daf = uuid.uuid4()
        recipient = uuid.uuid4()
        donor = uuid.uuid4()
        r = RelationshipDAFConduit.objects.create(
            daf_uuid=daf,
            recipient_uuid=recipient,
            donor_uuid=donor,
            data_source="irs_990",
        )
        assert r.relationship_uuid is not None
        assert r.donor_uuid == donor

    def test_daf_conduit_without_known_donor(self):
        r = RelationshipDAFConduit.objects.create(
            daf_uuid=uuid.uuid4(),
            recipient_uuid=uuid.uuid4(),
        )
        assert r.donor_uuid is None

    def test_query_recipients_through_daf(self):
        daf = uuid.uuid4()
        recipients = [uuid.uuid4() for _ in range(4)]
        for rec in recipients:
            RelationshipDAFConduit.objects.create(daf_uuid=daf, recipient_uuid=rec)
        qs = RelationshipDAFConduit.objects.filter(daf_uuid=daf)
        assert qs.count() == 4
