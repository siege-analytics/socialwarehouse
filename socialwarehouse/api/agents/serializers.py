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
            "source_system_id", "formation_date", "termination_date",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id", "entity_uuid", "name",
            "industry_code", "industry_system",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = [
            "id", "classification_uuid", "agent_uuid", "agent_type",
            "classification_type", "value",
            "effective_from", "effective_to",
            "data_source", "jurisdiction_state",
        ]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id", "role_uuid", "agent_uuid", "agent_type",
            "role_type", "counterparty_uuid", "counterparty_type",
            "effective_from", "effective_to",
            "data_source", "jurisdiction_state",
        ]
