from rest_framework import serializers

from socialwarehouse.transactions.models import (
    Contribution,
    Expenditure,
    Obligation,
    Transfer,
)


class ContributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contribution
        fields = [
            "id", "transaction_uuid", "transaction_type",
            "from_agent_uuid", "from_agent_type",
            "to_agent_uuid", "to_agent_type",
            "amount", "transaction_date", "description",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class ExpenditureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expenditure
        fields = [
            "id", "transaction_uuid", "transaction_type",
            "from_agent_uuid", "from_agent_type",
            "to_agent_uuid", "to_agent_type",
            "amount", "transaction_date", "description",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = [
            "id", "transaction_uuid", "transaction_type",
            "from_agent_uuid", "from_agent_type",
            "to_agent_uuid", "to_agent_type",
            "amount", "transaction_date", "description",
            "data_source", "jurisdiction_state", "source_record_id",
        ]


class ObligationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Obligation
        fields = [
            "id", "obligation_uuid", "obligation_type",
            "original_amount", "current_balance", "status",
            "agent_uuid", "agent_type",
            "counterparty_uuid", "counterparty_type",
            "data_source", "jurisdiction_state",
        ]
