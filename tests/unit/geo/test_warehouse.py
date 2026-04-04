"""Unit tests for socialwarehouse.warehouse models."""

from django.test import TestCase


class TestDimGeography(TestCase):
    """Test DimGeography model."""

    def test_create_geography(self):
        from socialwarehouse.warehouse.models import DimGeography

        geo = DimGeography.objects.create(
            geoid="06037",
            name="Los Angeles County",
            vintage_year=2020,
            summary_level="county",
            state_fips="06",
            is_current=True,
        )
        assert str(geo) == "Los Angeles County (06037, 2020)"
        assert geo.is_current is True

    def test_unique_together(self):
        from django.db import IntegrityError
        from socialwarehouse.warehouse.models import DimGeography

        DimGeography.objects.create(
            geoid="06037", name="LA County", vintage_year=2020, summary_level="county",
        )
        with self.assertRaises(IntegrityError):
            DimGeography.objects.create(
                geoid="06037", name="LA County dupe", vintage_year=2020, summary_level="county",
            )

    def test_parent_drill_up(self):
        from socialwarehouse.warehouse.models import DimGeography

        state = DimGeography.objects.create(
            geoid="06", name="California", vintage_year=2020, summary_level="state",
        )
        county = DimGeography.objects.create(
            geoid="06037", name="Los Angeles County", vintage_year=2020,
            summary_level="county", state_fips="06", parent=state,
        )
        assert county.parent == state
        assert state.children.count() == 1


class TestDimSurvey(TestCase):
    def test_create_survey(self):
        from socialwarehouse.warehouse.models import DimSurvey

        survey = DimSurvey.objects.create(
            survey_type="acs5", vintage_year=2022,
        )
        assert "ACS 5-Year" in str(survey)


class TestDimCensusVariable(TestCase):
    def test_create_variable(self):
        from socialwarehouse.warehouse.models import DimCensusVariable

        var = DimCensusVariable.objects.create(
            table_id="B01001",
            variable_code="B01001_001E",
            label="Total population",
            concept="SEX BY AGE",
            variable_type="extensive",
            dataset="acs5",
        )
        assert var.is_estimate is True
        assert var.is_moe is False


class TestFactACSEstimate(TestCase):
    def test_auto_compute_reliability(self):
        from socialwarehouse.warehouse.models import DimGeography, DimSurvey, DimCensusVariable, FactACSEstimate

        geo = DimGeography.objects.create(
            geoid="06037", name="LA County", vintage_year=2020, summary_level="county",
        )
        survey = DimSurvey.objects.create(survey_type="acs5", vintage_year=2022)
        var = DimCensusVariable.objects.create(
            table_id="B01001", variable_code="B01001_001E",
            label="Total pop", dataset="acs5",
        )

        fact = FactACSEstimate(
            geography=geo, variable=var, survey=survey,
            estimate=10000, margin_of_error=500,
        )
        fact.save()

        assert fact.coefficient_of_variation is not None
        assert fact.reliability == "high"  # CV should be ~3%
