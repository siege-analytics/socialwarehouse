"""Serializers for warehouse star-schema models."""

from rest_framework import serializers

from socialwarehouse.warehouse.models import (
    DimGeography,
    FactACSEstimate,
    FactElectionResult,
)


class DimGeographySerializer(serializers.ModelSerializer):
    class Meta:
        model = DimGeography
        fields = [
            "id", "geoid", "name", "summary_level", "state_fips",
            "parent", "vintage_year", "is_current",
            "area_land", "area_water",
        ]


class FactElectionResultSerializer(serializers.ModelSerializer):
    geography_geoid = serializers.CharField(source="geography.geoid", read_only=True)
    geography_name = serializers.CharField(source="geography.name", read_only=True)

    class Meta:
        model = FactElectionResult
        fields = [
            "id", "geography", "geography_geoid", "geography_name",
            "election_date", "office", "party", "candidate_name",
            "votes", "total_votes", "vote_share",
            "created_at",
        ]


class FactACSEstimateSerializer(serializers.ModelSerializer):
    geography_geoid = serializers.CharField(source="geography.geoid", read_only=True)
    variable_code = serializers.CharField(source="variable.variable_code", read_only=True)
    survey_type = serializers.CharField(source="survey.survey_type", read_only=True)

    class Meta:
        model = FactACSEstimate
        fields = [
            "id", "geography", "geography_geoid",
            "variable", "variable_code",
            "survey", "survey_type",
            "estimate", "margin_of_error", "coefficient_of_variation", "reliability",
            "created_at",
        ]
