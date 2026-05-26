from rest_framework import serializers

from socialwarehouse.political.models import (
    Election,
    ElectoralContest,
    Office,
    OfficeTerm,
    Seat,
)


class OfficeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Office
        fields = [
            "id", "entity_uuid", "name",
            "jurisdiction_level", "jurisdiction_state",
            "chamber", "district_number",
        ]


class SeatSerializer(serializers.ModelSerializer):
    office_name = serializers.CharField(source="office.name", read_only=True)

    class Meta:
        model = Seat
        fields = [
            "id", "seat_uuid", "office", "office_name",
            "redistricting_plan_id",
            "effective_from", "effective_to",
            "boundary_geoid", "is_current",
        ]


class ElectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Election
        fields = [
            "id", "election_uuid", "election_date",
            "jurisdiction_level", "jurisdiction_state",
            "election_type", "year",
            "data_source",
        ]


class ElectoralContestSerializer(serializers.ModelSerializer):
    office_name = serializers.CharField(source="office.name", read_only=True)
    election_date = serializers.DateField(source="election.election_date", read_only=True)

    class Meta:
        model = ElectoralContest
        fields = [
            "id", "contest_uuid",
            "election", "election_date",
            "office", "office_name",
            "seat",
        ]


class OfficeTermSerializer(serializers.ModelSerializer):
    office_name = serializers.CharField(source="office.name", read_only=True)

    class Meta:
        model = OfficeTerm
        fields = [
            "id", "office", "office_name",
            "person_uuid", "start_date", "end_date",
            "term_type", "congress_number",
            "data_source", "is_current",
        ]
