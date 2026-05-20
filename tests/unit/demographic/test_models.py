"""Tests for D Phase 1a (SW#192): ACSVariable + ACSEstimate models.

Migration 0001 ran seed_acs_variables (the curated subset); these
tests verify the seeded state + the constraints + cross-vintage shape.
"""

from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class TestACSVariableSeed(TestCase):
    """Curated catalog seeded by migration 0001 + idempotent reseed."""

    def test_curated_variables_present(self):
        from socialwarehouse.demographic.models import ACSVariable

        # 12 curated variables per seed_acs_variables.CURATED_VARIABLES.
        assert ACSVariable.objects.count() >= 12

        total_pop = ACSVariable.objects.get(variable_code="B01001_001E")
        assert total_pop.concept == "SEX BY AGE"
        assert total_pop.universe == "Total population"
        assert total_pop.predicate_type == "int"

    def test_seed_command_is_idempotent(self):
        from socialwarehouse.demographic.models import ACSVariable

        before = ACSVariable.objects.count()
        call_command("seed_acs_variables", verbosity=0)
        assert ACSVariable.objects.count() == before

    def test_seed_command_dry_run(self):
        from socialwarehouse.demographic.models import ACSVariable

        before = ACSVariable.objects.count()
        call_command("seed_acs_variables", "--dry-run", verbosity=0, stdout=StringIO())
        assert ACSVariable.objects.count() == before


class TestACSEstimateModel(TestCase):
    """Long-format estimate model: one row per (vintage, variable, boundary, geoid)."""

    def setUp(self):
        from socialwarehouse.demographic.models import ACSVariable
        from socialwarehouse.geo.models import ACSVintage

        self.variable = ACSVariable.objects.get(variable_code="B19013_001E")
        self.vintage = ACSVintage.objects.filter(span_years=5).order_by("-end_year").first()
        assert self.vintage is not None, "ACS 5-year vintages should be seeded by migration 0004"

    def test_create_estimate(self):
        from socialwarehouse.demographic.models import ACSEstimate

        e = ACSEstimate.objects.create(
            vintage=self.vintage,
            variable=self.variable,
            boundary_type="tract",
            geoid="06037103300",
            value=Decimal("89231.50"),
            moe=Decimal("4321.00"),
        )
        e.refresh_from_db()
        assert e.value == Decimal("89231.5000")
        assert e.moe == Decimal("4321.0000")
        assert "B19013_001E" in str(e)

    def test_unique_per_vintage_variable_boundary_geoid(self):
        from django.db import IntegrityError
        from socialwarehouse.demographic.models import ACSEstimate

        ACSEstimate.objects.create(
            vintage=self.vintage,
            variable=self.variable,
            boundary_type="tract",
            geoid="06037103300",
            value=Decimal("89231.50"),
        )
        with self.assertRaises(IntegrityError):
            ACSEstimate.objects.create(
                vintage=self.vintage,
                variable=self.variable,
                boundary_type="tract",
                geoid="06037103300",
                value=Decimal("90000"),
            )

    def test_value_is_optional_with_annotation(self):
        from socialwarehouse.demographic.models import ACSEstimate

        # Census jam value "*" means "controlled to a fixed value; no MOE."
        e = ACSEstimate.objects.create(
            vintage=self.vintage,
            variable=self.variable,
            boundary_type="tract",
            geoid="06037103300",
            value=None,
            moe=None,
            annotation="*",
        )
        assert e.value is None
        assert e.annotation == "*"

    def test_estimate_belongs_to_polymorphic_vintage(self):
        """ACSEstimate.vintage FKs the Vintage parent; cross-kind queries
        confirm the limit_choices_to is advisory (not enforced at DB level).
        """
        from socialwarehouse.geo.models import Vintage
        from socialwarehouse.demographic.models import ACSEstimate

        e = ACSEstimate.objects.create(
            vintage=self.vintage,
            variable=self.variable,
            boundary_type="county", geoid="06037",
            value=Decimal("75000"),
        )
        # The reverse accessor on Vintage works.
        v = Vintage.objects.get(pk=self.vintage.pk)
        assert e in v.acs_estimates.all()

    def test_cross_vintage_lookup(self):
        from socialwarehouse.demographic.models import ACSEstimate
        from socialwarehouse.geo.models import ACSVintage

        v1 = ACSVintage.objects.filter(span_years=5).order_by("-end_year")[0]
        v2 = ACSVintage.objects.filter(span_years=5).order_by("-end_year")[1]

        for v, val in [(v1, Decimal("90000")), (v2, Decimal("85000"))]:
            ACSEstimate.objects.create(
                vintage=v,
                variable=self.variable,
                boundary_type="tract",
                geoid="06037103300",
                value=val,
            )

        rows = (
            ACSEstimate.objects
            .filter(variable=self.variable, boundary_type="tract", geoid="06037103300")
            .select_related("vintage")
            .order_by("vintage__effective_from")
        )
        values = [r.value for r in rows]
        assert values == [Decimal("85000.0000"), Decimal("90000.0000")]
