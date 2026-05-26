from rest_framework import serializers

from socialwarehouse.events.models import (
    CorporateEvent,
    ElectoralEvent,
    Event,
    EventParticipant,
    SpatioTemporalEvent,
)


class EventParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventParticipant
        fields = [
            "id", "agent_uuid", "agent_type", "role_in_event",
        ]


class CorporateEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorporateEvent
        fields = [
            "corporate_event_type",
            "predecessor_uuid", "successor_uuid",
            "relationship_uuid",
        ]


class SpatioTemporalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpatioTemporalEvent
        fields = [
            "spatiotemporal_event_type",
            "redistricting_plan_id",
            "affected_boundary_type",
            "affected_jurisdiction_state",
        ]


class ElectoralEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ElectoralEvent
        fields = [
            "electoral_event_type",
            "contest_uuid",
            "is_certified", "is_recount",
        ]


class EventSerializer(serializers.ModelSerializer):
    participants = EventParticipantSerializer(many=True, read_only=True)
    corporate_detail = CorporateEventSerializer(read_only=True)
    spatiotemporal_detail = SpatioTemporalEventSerializer(read_only=True)
    electoral_detail = ElectoralEventSerializer(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "event_uuid", "event_type",
            "event_date", "year", "description",
            "jurisdiction_state", "data_source",
            "participants",
            "corporate_detail",
            "spatiotemporal_detail",
            "electoral_detail",
        ]


class EventListSerializer(serializers.ModelSerializer):
    participant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "event_uuid", "event_type",
            "event_date", "year",
            "jurisdiction_state", "data_source",
            "participant_count",
        ]
