import uuid
from datetime import date

import pytest
from django.test import TestCase

from socialwarehouse.agents.models import Committee
from socialwarehouse.core.mixins import generate_entity_uuid5


@pytest.mark.django_db
class TestCommitteeLifecycle(TestCase):
    def test_create_active_committee(self):
        eu = generate_entity_uuid5("fec", "C00123456")
        c = Committee.objects.create(
            entity_uuid=eu,
            name="Friends of Democracy PAC",
            committee_type="pac",
            source_system_id="C00123456",
            data_source="fec",
            jurisdiction_level="federal",
            formation_date=date(2020, 1, 15),
        )
        assert c.is_active is True
        assert c.name == "Friends of Democracy PAC"
        assert c.committee_type == "pac"

    def test_terminated_committee(self):
        eu = generate_entity_uuid5("fec", "C00999999")
        c = Committee.objects.create(
            entity_uuid=eu,
            name="Old Campaign Fund",
            committee_type="campaign",
            source_system_id="C00999999",
            data_source="fec",
            formation_date=date(2018, 3, 1),
            termination_date=date(2020, 12, 31),
        )
        assert c.is_active is False

    def test_name_history_tracks_changes(self):
        eu = generate_entity_uuid5("fec", "C00111111")
        c = Committee.objects.create(
            entity_uuid=eu,
            name="New Name PAC",
            committee_type="pac",
            source_system_id="C00111111",
            data_source="fec",
            name_history=[
                {"name": "Old Name PAC", "effective_from": "2018-01-01", "effective_to": "2022-06-30"},
                {"name": "New Name PAC", "effective_from": "2022-07-01", "effective_to": None},
            ],
        )
        assert len(c.name_history) == 2
        assert c.name_history[0]["name"] == "Old Name PAC"

    def test_natural_key_uniqueness(self):
        eu1 = generate_entity_uuid5("fec", "C00222222")
        Committee.objects.create(
            entity_uuid=eu1,
            name="First PAC",
            source_system_id="C00222222",
            data_source="fec",
        )
        eu2 = generate_entity_uuid5("fec", "C00222222-dup")
        with pytest.raises(Exception):
            Committee.objects.create(
                entity_uuid=eu2,
                name="Duplicate PAC",
                source_system_id="C00222222",
                data_source="fec",
            )

    def test_str_representation(self):
        eu = generate_entity_uuid5("fec", "C00333333")
        c = Committee(
            entity_uuid=eu,
            name="Test PAC",
            committee_type="pac",
            source_system_id="C00333333",
            data_source="fec",
        )
        assert "Test PAC" in str(c)
        assert "pac" in str(c)
        assert "active" in str(c)
