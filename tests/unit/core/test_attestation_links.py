"""Tests for the three attestation variant-linking abstract base classes.

The bases ship abstract (no template-side tables). These tests stand in
as the adopter: each declares a concrete subclass, materializes its
table with the schema editor in setUpClass, and exercises real DB
behavior against the central Attestation. The concrete models are
test-only (no migration), so they do not affect the template schema.
"""

import uuid
from decimal import Decimal

import pytest
from django.db import connection, models
from django.test import TransactionTestCase

from socialwarehouse.core.attestation import Attestation
from socialwarehouse.core.attestation_links import (
    RESOLUTION_RESOLVED,
    AttestationJunction,
    AttestationSubtypeLink,
    ResolutionAttestation,
)


# Test-only concrete subclasses standing in for adopter models. Defined
# under the sw_core label; they carry no migration, so setUpClass builds
# their tables with the schema editor and tearDownClass drops them.
class CommitteeAttestationLink(AttestationSubtypeLink):
    class Meta:
        app_label = "sw_core"


class FilingAttestationLink(AttestationJunction):
    filing_id = models.UUIDField()

    class Meta:
        app_label = "sw_core"
        unique_together = [("filing_id", "attestation")]


class AddressResolutionAttestation(ResolutionAttestation):
    class Meta:
        app_label = "sw_core"


def _mk_attestation():
    return Attestation.objects.create(
        entity_id=uuid.uuid4(),
        entity_subtype="committee",
        attestation_kind="fec",
        data_source="fec",
    )


class _SchemaManaged(TransactionTestCase):
    """Base that creates/drops one test-only concrete model's table."""

    concrete_model = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The concrete stand-in models are declared at module level, so they
        # stay registered in the app registry (with FKs to Attestation) for the
        # whole test session. Their tables must therefore persist for the whole
        # session too — otherwise a later test that deletes an Attestation (e.g.
        # the Event-canonicalization SET_NULL tests) traverses these reverse
        # relations via Django's delete-collector and queries a dropped table.
        # Create idempotently and do NOT drop per-class; the test DB teardown
        # removes the tables at session end.
        if cls.concrete_model._meta.db_table not in connection.introspection.table_names():
            with connection.schema_editor() as editor:
                editor.create_model(cls.concrete_model)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()


@pytest.mark.django_db(transaction=True)
class TestAttestationSubtypeLink(_SchemaManaged):
    concrete_model = CommitteeAttestationLink

    def test_abstract(self):
        assert AttestationSubtypeLink._meta.abstract is True

    def test_adopter_subclass_links_to_attestation(self):
        att = _mk_attestation()
        link = CommitteeAttestationLink.objects.create(
            attestation=att, entity_subtype="committee", source_type="fec_bulk"
        )
        assert link.attestation == att
        assert link.entity_subtype == "committee"
        # Reverse accessor uses the %(class)s pattern on the base FK.
        assert att.committeeattestationlink_links.count() == 1


@pytest.mark.django_db(transaction=True)
class TestAttestationJunction(_SchemaManaged):
    concrete_model = FilingAttestationLink

    def test_abstract(self):
        assert AttestationJunction._meta.abstract is True

    def test_adopter_junction_many_to_many(self):
        filing_id = uuid.uuid4()
        a1 = _mk_attestation()
        a2 = _mk_attestation()
        FilingAttestationLink.objects.create(filing_id=filing_id, attestation=a1)
        FilingAttestationLink.objects.create(filing_id=filing_id, attestation=a2)
        # One filing, two attestations.
        assert FilingAttestationLink.objects.filter(filing_id=filing_id).count() == 2
        assert a1.filingattestationlink_junctions.count() == 1


@pytest.mark.django_db(transaction=True)
class TestResolutionAttestation(_SchemaManaged):
    concrete_model = AddressResolutionAttestation

    def test_abstract(self):
        assert ResolutionAttestation._meta.abstract is True

    def test_adopter_resolution_records_raw_and_resolved(self):
        resolved_id = uuid.uuid4()
        row = AddressResolutionAttestation.objects.create(
            raw_input={"line1": "123 Main St", "zip": "78701"},
            resolved_entity_id=resolved_id,
            resolved_entity_subtype="address",
            resolution_status=RESOLUTION_RESOLVED,
            resolution_confidence=Decimal("0.9900"),
            resolver_source="census_geocoder",
            run_id=uuid.uuid4(),
        )
        assert row.is_resolved is True
        assert row.raw_input["zip"] == "78701"
        assert row.resolved_entity_id == resolved_id

    def test_unresolved_default_is_not_resolved(self):
        pending = AddressResolutionAttestation.objects.create(raw_input={"line1": "garbled"})
        # Default status is pending; not resolved without a target.
        assert pending.is_resolved is False
