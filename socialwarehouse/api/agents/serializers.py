from rest_framework import serializers

from socialwarehouse.agents.models import (
    Classification,
    Committee,
    Organization,
    Role,
)
from socialwarehouse.warehouse.models import DimPerson


class DimPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = DimPerson
        fields = [
            "id", "entity_uuid", "first_name", "last_name",
            "name_suffix", "data_source", "jurisdiction_state",
            "source_record_id",
        ]


class CommitteeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Committee
        fields = [
            "id", "entity_uuid", "name", "committee_type",
            "designation", "filing_frequency",
            "treasurer_uuid", "connected_org_uuid",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id", "entity_uuid", "name", "organization_type",
            "industry_code",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = [
            "id", "agent_uuid", "agent_type",
            "classification_type", "classification_value",
            "effective_from", "effective_to",
            "data_source", "jurisdiction_state",
        ]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id", "agent_uuid", "agent_type",
            "role_type", "role_context",
            "context_entity_uuid", "context_entity_type",
            "effective_from", "effective_to",
            "data_source", "jurisdiction_state",
        ]
