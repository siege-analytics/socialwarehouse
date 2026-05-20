"""Tests for SW#194 F Phase 2: SpecialDistrictAttributes.

Schema-only PR — no auto-ingest. These tests pin the schema contract
(unique key, choices, multi-year coexistence) so future loaders can
write against a stable shape.
"""

from django.db import IntegrityError
from django.test import TestCase


class TestSpecialDistrictAttributesSchema(TestCase):

    def test_create_minimal_row(self):
        from socialwarehouse.civic.models import SpecialDistrictAttributes

        row = SpecialDistrictAttributes.objects.create(
            boundary_type="fire_district",
            geoid="0612345",
            source_year=2022,
        )
        assert row.pk is not None
        assert row.function == ""  # default
        assert row.annual_revenue is None

    def test_unique_per_boundary_geoid_year(self):
        from socialwarehouse.civic.models import SpecialDistrictAttributes

        SpecialDistrictAttributes.objects.create(
            boundary_type="fire_district",
            geoid="0612345",
            source_year=2022,
            governing_body="First Board",
        )
        with self.assertRaises(IntegrityError):
            SpecialDistrictAttributes.objects.create(
                boundary_type="fire_district",
                geoid="0612345",
                source_year=2022,
                governing_body="Duplicate",
            )

    def test_same_geoid_different_year_allowed(self):
        """Multiple snapshots of the same district across years."""
        from socialwarehouse.civic.models import SpecialDistrictAttributes

        SpecialDistrictAttributes.objects.create(
            boundary_type="fire_district",
            geoid="0612345",
            source_year=2017,
        )
        SpecialDistrictAttributes.objects.create(
            boundary_type="fire_district",
            geoid="0612345",
            source_year=2022,
        )
        assert SpecialDistrictAttributes.objects.filter(geoid="0612345").count() == 2

    def test_same_geoid_different_boundary_type_allowed(self):
        """Same TIGER GEOID for two different special-district kinds
        is allowed (and theoretically possible since each kind has its
        own TIGER table)."""
        from socialwarehouse.civic.models import SpecialDistrictAttributes

        SpecialDistrictAttributes.objects.create(
            boundary_type="fire_district",
            geoid="0612345",
            source_year=2022,
        )
        SpecialDistrictAttributes.objects.create(
            boundary_type="water_district",
            geoid="0612345",
            source_year=2022,
        )
        assert SpecialDistrictAttributes.objects.filter(geoid="0612345").count() == 2

    def test_all_seven_kinds_accepted(self):
        from socialwarehouse.civic.models import SpecialDistrictAttributes
        from socialwarehouse.civic.models.special_district import (
            _SPECIAL_DISTRICT_BOUNDARY_TYPES,
        )

        for kind in _SPECIAL_DISTRICT_BOUNDARY_TYPES:
            SpecialDistrictAttributes.objects.create(
                boundary_type=kind,
                geoid="9999999",
                source_year=2022,
            )
        assert (
            SpecialDistrictAttributes.objects.filter(geoid="9999999").count()
            == len(_SPECIAL_DISTRICT_BOUNDARY_TYPES)
        )
