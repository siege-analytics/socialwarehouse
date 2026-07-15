import uuid
from datetime import datetime, timezone

import pytest
from django.db import IntegrityError, transaction
from django.test import TestCase

from socialwarehouse.agents.models import Committee
from socialwarehouse.core.agent import Agent
from socialwarehouse.core.attestation import (
    ATTESTATION_KIND_FEC,
    TIER_AUTHORITATIVE,
    TIER_SECONDARY,
    Attestation,
    FECAttestation,
)
from socialwarehouse.core.mixins import generate_entity_uuid5


@pytest.mark.django_db
class TestAttestationCanonical(TestCase):
    def setUp(self):
        self.entity_id = uuid.uuid4()

    def _mk(self, **kw):
        defaults = dict(
            entity_id=self.entity_id,
            entity_subtype="committee",
            attestation_kind=ATTESTATION_KIND_FEC,
            data_source="fec",
        )
        defaults.update(kw)
        return Attestation.objects.create(**defaults)

    def test_entity_uuid_autoassigned_uuid4(self):
        a = self._mk()
        assert a.entity_uuid is not None
        # Distinct rows get distinct artifact UUIDs.
        b = self._mk(sequence=1)
        assert a.entity_uuid != b.entity_uuid

    def test_multi_source_provenance_one_canonical(self):
        # Three attestations of the same entity; one is canonical.
        self._mk(sequence=0, attestation_source_tier=TIER_SECONDARY)
        self._mk(sequence=1, attestation_source_tier=TIER_SECONDARY)
        self._mk(sequence=2, attestation_source_tier=TIER_AUTHORITATIVE, is_canonical=True)

        qs = Attestation.for_entity("committee", self.entity_id)
        assert qs.count() == 3
        canonical = Attestation.canonical_for("committee", self.entity_id, ATTESTATION_KIND_FEC)
        assert canonical is not None
        assert canonical.is_canonical is True
        assert canonical.attestation_source_tier == TIER_AUTHORITATIVE

    def test_only_one_canonical_per_entity_kind(self):
        self._mk(sequence=0, is_canonical=True)
        with transaction.atomic():
            with pytest.raises(IntegrityError):
                self._mk(sequence=1, is_canonical=True)

    def test_non_canonical_duplicates_allowed(self):
        # The partial constraint only restricts is_canonical=True rows.
        self._mk(sequence=0, is_canonical=False)
        self._mk(sequence=1, is_canonical=False)
        assert Attestation.for_entity("committee", self.entity_id, is_canonical=False).count() == 2

    def test_amendment_via_new_canonical_attestation(self):
        # Amendment = supersede the old canonical with a new one.
        old = self._mk(sequence=0, is_canonical=True, attested_values={"amount": 100})
        old.is_canonical = False
        old.save(update_fields=["is_canonical"])
        new = self._mk(sequence=1, is_canonical=True, attested_values={"amount": 250})
        assert Attestation.canonical_for("committee", self.entity_id, ATTESTATION_KIND_FEC) == new
        assert new.attested_values["amount"] == 250


@pytest.mark.django_db
class TestAttestationEntityResolution(TestCase):
    def test_get_entity_resolves_agent(self):
        agent = Agent.objects.create(subtype="committee", data_source="fec", source_record_id="C9")
        a = Attestation.objects.create(
            entity_id=agent.entity_uuid,
            entity_subtype="agent",
            attestation_kind=ATTESTATION_KIND_FEC,
            data_source="fec",
        )
        assert a.get_entity() == agent

    def test_get_entity_resolves_committee(self):
        eu = generate_entity_uuid5("fec", "C77")
        committee = Committee.objects.create(
            entity_uuid=eu,
            name="Resolved PAC",
            committee_type="pac",
            source_system_id="C77",
            data_source="fec",
        )
        a = Attestation.objects.create(
            entity_id=eu,
            entity_subtype="committee",
            attestation_kind=ATTESTATION_KIND_FEC,
            data_source="fec",
        )
        assert a.get_entity() == committee

    def test_get_entity_unknown_subtype_raises(self):
        a = Attestation.objects.create(
            entity_id=uuid.uuid4(),
            entity_subtype="nonexistent_kind",
            attestation_kind=ATTESTATION_KIND_FEC,
            data_source="fec",
        )
        with pytest.raises(LookupError):
            a.get_entity()

    def test_get_entity_missing_row_returns_none(self):
        # Registered subtype but no matching row -> None (legit "not found").
        a = Attestation.objects.create(
            entity_id=uuid.uuid4(),
            entity_subtype="agent",
            attestation_kind=ATTESTATION_KIND_FEC,
            data_source="fec",
        )
        assert a.get_entity() is None


@pytest.mark.django_db
class TestFECAttestationSubclass(TestCase):
    def test_create_fec_attestation_sets_kind(self):
        f = FECAttestation.objects.create(
            entity_id=uuid.uuid4(),
            entity_subtype="filing",
            data_source="fec",
            fec_form_type="F3X",
            parser_version="hydra-2.1",
            attested_at=datetime(2024, 1, 5, tzinfo=timezone.utc),
        )
        # attestation_kind defaults to 'fec' for the FEC subclass.
        assert f.attestation_kind == ATTESTATION_KIND_FEC
        assert f.fec_form_type == "F3X"
        assert f.parser_version == "hydra-2.1"

    def test_mti_parent_row_present(self):
        f = FECAttestation.objects.create(
            entity_id=uuid.uuid4(),
            entity_subtype="filing",
            data_source="fec",
            fec_form_type="F3",
        )
        # Multi-table inheritance: a parent Attestation row exists with the same pk.
        parent = Attestation.objects.get(pk=f.pk)
        assert parent.attestation_kind == ATTESTATION_KIND_FEC
        assert parent.entity_subtype == "filing"
        # And it downcasts back to the FEC subclass.
        assert parent.fecattestation == f

    def test_fec_attestation_has_own_table(self):
        assert FECAttestation._meta.db_table == "sw_fec_attestation"
        assert Attestation._meta.db_table == "sw_attestation"
