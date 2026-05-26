import uuid

import pytest
from django.test import TestCase

from socialwarehouse.core.models import EntityIdentifier


@pytest.mark.django_db
class TestEntityIdentifierRegister(TestCase):
    def test_register_creates_row(self):
        eu = uuid.uuid4()
        obj, created = EntityIdentifier.register(
            entity_uuid=eu,
            identifier_type="vendor_voter_id",
            identifier_value="TX-123456",
            data_source="targetsmart",
        )
        assert created is True
        assert obj.entity_uuid == eu
        assert obj.identifier_type == "vendor_voter_id"
        assert obj.identifier_value == "TX-123456"
        assert obj.data_source == "targetsmart"

    def test_register_idempotent(self):
        eu = uuid.uuid4()
        kwargs = dict(
            entity_uuid=eu,
            identifier_type="vendor_voter_id",
            identifier_value="TX-999",
            data_source="targetsmart",
        )
        _, created1 = EntityIdentifier.register(**kwargs)
        _, created2 = EntityIdentifier.register(**kwargs)
        assert created1 is True
        assert created2 is False
        assert EntityIdentifier.objects.filter(entity_uuid=eu).count() == 1

    def test_register_with_jurisdiction(self):
        eu = uuid.uuid4()
        obj, _ = EntityIdentifier.register(
            entity_uuid=eu,
            identifier_type="state_voter_id",
            identifier_value="SV-001",
            data_source="sos",
            jurisdiction_level="state",
            jurisdiction_state="TX",
        )
        assert obj.jurisdiction_level == "state"
        assert obj.jurisdiction_state == "TX"


@pytest.mark.django_db
class TestEntityIdentifierResolve(TestCase):
    def test_resolve_finds_current(self):
        eu = uuid.uuid4()
        EntityIdentifier.register(
            entity_uuid=eu,
            identifier_type="vendor_voter_id",
            identifier_value="TX-555",
            data_source="targetsmart",
        )
        qs = EntityIdentifier.resolve("vendor_voter_id", "TX-555")
        assert qs.count() == 1
        assert qs.first().entity_uuid == eu

    def test_resolve_filters_by_source(self):
        eu1 = uuid.uuid4()
        eu2 = uuid.uuid4()
        EntityIdentifier.register(
            entity_uuid=eu1,
            identifier_type="vendor_voter_id",
            identifier_value="SHARED-ID",
            data_source="targetsmart",
        )
        EntityIdentifier.register(
            entity_uuid=eu2,
            identifier_type="vendor_voter_id",
            identifier_value="SHARED-ID",
            data_source="l2",
        )
        qs = EntityIdentifier.resolve("vendor_voter_id", "SHARED-ID", data_source="l2")
        assert qs.count() == 1
        assert qs.first().entity_uuid == eu2

    def test_resolve_excludes_expired(self):
        from django.utils import timezone

        eu = uuid.uuid4()
        obj, _ = EntityIdentifier.register(
            entity_uuid=eu,
            identifier_type="vendor_voter_id",
            identifier_value="TX-OLD",
            data_source="targetsmart",
        )
        obj.valid_to = timezone.now()
        obj.save()
        qs = EntityIdentifier.resolve("vendor_voter_id", "TX-OLD")
        assert qs.count() == 0

    def test_resolve_no_match(self):
        qs = EntityIdentifier.resolve("vendor_voter_id", "NONEXISTENT")
        assert qs.count() == 0
