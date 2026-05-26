import pytest
from django.test import TestCase

from socialwarehouse.agents.models import Organization
from socialwarehouse.core.mixins import generate_entity_uuid5


@pytest.mark.django_db
class TestOrganization(TestCase):
    def test_create_with_naics(self):
        eu = generate_entity_uuid5("duns", "123456789")
        o = Organization.objects.create(
            entity_uuid=eu,
            name="Acme Consulting LLC",
            industry_code="541611",
            industry_system="naics",
            data_source="duns",
            jurisdiction_level="federal",
            jurisdiction_state="TX",
        )
        assert o.name == "Acme Consulting LLC"
        assert o.industry_code == "541611"
        assert o.industry_system == "naics"

    def test_create_without_industry(self):
        eu = generate_entity_uuid5("manual", "org-no-industry")
        o = Organization.objects.create(
            entity_uuid=eu,
            name="Unknown Corp",
            data_source="manual",
        )
        assert o.industry_code == ""
        assert o.industry_system == "naics"

    def test_str_with_industry(self):
        eu = generate_entity_uuid5("duns", "str-test")
        o = Organization(
            entity_uuid=eu,
            name="Big Corp",
            industry_code="511210",
        )
        assert "Big Corp" in str(o)
        assert "511210" in str(o)

    def test_str_without_industry(self):
        eu = generate_entity_uuid5("duns", "str-test-2")
        o = Organization(
            entity_uuid=eu,
            name="Small LLC",
            industry_code="",
        )
        result = str(o)
        assert "Small LLC" in result
        assert "[" not in result

    def test_entity_uuid_unique(self):
        eu = generate_entity_uuid5("duns", "unique-test")
        Organization.objects.create(
            entity_uuid=eu,
            name="First Org",
            data_source="duns",
        )
        with pytest.raises(Exception):
            Organization.objects.create(
                entity_uuid=eu,
                name="Duplicate Org",
                data_source="other",
            )
