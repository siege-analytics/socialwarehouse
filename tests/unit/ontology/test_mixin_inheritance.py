"""Verify every ontology model inherits from the correct abstract mixins.

These are structural tests: they assert the class hierarchy is correct
and that expected fields are present on each model. They don't need
a database — they inspect the Django meta layer.
"""

import uuid

from django.test import TestCase

from socialwarehouse.core.mixins import (
    IdentifiableModel,
    SourceAwareModel,
    generate_entity_uuid5,
)


class TestSourceAwareInheritance(TestCase):
    """Every model that inherits SourceAwareModel gets its fields."""

    def _assert_source_aware(self, model_class):
        field_names = {f.name for f in model_class._meta.get_fields()}
        assert "data_source" in field_names
        assert "jurisdiction_level" in field_names
        assert "jurisdiction_state" in field_names
        assert "source_record_id" in field_names
        assert "ingested_at" in field_names
        assert issubclass(model_class, SourceAwareModel)

    def test_committee(self):
        from socialwarehouse.agents.models import Committee
        self._assert_source_aware(Committee)

    def test_organization(self):
        from socialwarehouse.agents.models import Organization
        self._assert_source_aware(Organization)

    def test_contribution(self):
        from socialwarehouse.transactions.models import Contribution
        self._assert_source_aware(Contribution)

    def test_expenditure(self):
        from socialwarehouse.transactions.models import Expenditure
        self._assert_source_aware(Expenditure)

    def test_transfer(self):
        from socialwarehouse.transactions.models import Transfer
        self._assert_source_aware(Transfer)

    def test_obligation(self):
        from socialwarehouse.transactions.models import Obligation
        self._assert_source_aware(Obligation)

    def test_event(self):
        from socialwarehouse.events.models import Event
        self._assert_source_aware(Event)


class TestIdentifiableInheritance(TestCase):
    """Every identity-bearing model inherits IdentifiableModel."""

    def _assert_identifiable(self, model_class):
        field_names = {f.name for f in model_class._meta.get_fields()}
        assert "entity_uuid" in field_names
        assert issubclass(model_class, IdentifiableModel)

    def test_committee(self):
        from socialwarehouse.agents.models import Committee
        self._assert_identifiable(Committee)

    def test_organization(self):
        from socialwarehouse.agents.models import Organization
        self._assert_identifiable(Organization)


class TestUUID5Determinism(TestCase):
    """UUID5 generation is deterministic across calls."""

    def test_same_inputs_same_uuid(self):
        u1 = generate_entity_uuid5("John", "Doe", "1980-01-01")
        u2 = generate_entity_uuid5("John", "Doe", "1980-01-01")
        assert u1 == u2

    def test_case_insensitive(self):
        u1 = generate_entity_uuid5("JOHN", "DOE")
        u2 = generate_entity_uuid5("john", "doe")
        assert u1 == u2

    def test_whitespace_insensitive(self):
        u1 = generate_entity_uuid5("  John ", " Doe  ")
        u2 = generate_entity_uuid5("John", "Doe")
        assert u1 == u2

    def test_none_handled(self):
        u1 = generate_entity_uuid5("John", None, "TX")
        u2 = generate_entity_uuid5("John", None, "TX")
        assert u1 == u2
        assert isinstance(u1, uuid.UUID)

    def test_different_inputs_different_uuid(self):
        u1 = generate_entity_uuid5("John", "Doe")
        u2 = generate_entity_uuid5("Jane", "Doe")
        assert u1 != u2
