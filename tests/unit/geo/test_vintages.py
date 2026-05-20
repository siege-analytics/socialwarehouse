"""Tests for the polymorphic Vintage models.

Template-readiness B PR #1 (SW#190): models exist as additive new
tables; ABP's FK is unchanged. Tests cover the parent + per-kind
subclass shape, `is_current` semantics, and the
`seed_known_vintages` management command's idempotency.
"""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class TestVintageParent(TestCase):
    """`Vintage`'s shared fields + `is_current` semantics."""

    def test_is_current_when_today_in_window(self):
        from socialwarehouse.geo.models import Vintage

        v = Vintage.objects.create(
            name="test", kind="acs",
            effective_from=date(2024, 1, 1),
            effective_to=date(2026, 1, 1),
        )
        assert v.is_current(on_date=date(2025, 6, 1))

    def test_is_current_false_after_window(self):
        from socialwarehouse.geo.models import Vintage

        v = Vintage.objects.create(
            name="old", kind="acs",
            effective_from=date(2020, 1, 1),
            effective_to=date(2023, 1, 1),
        )
        assert not v.is_current(on_date=date(2025, 6, 1))

    def test_is_current_false_before_window(self):
        from socialwarehouse.geo.models import Vintage

        v = Vintage.objects.create(
            name="future", kind="acs",
            effective_from=date(2030, 1, 1),
            effective_to=None,
        )
        assert not v.is_current(on_date=date(2025, 6, 1))

    def test_is_current_true_with_null_effective_to(self):
        from socialwarehouse.geo.models import Vintage

        v = Vintage.objects.create(
            name="ongoing", kind="acs",
            effective_from=date(2020, 1, 1),
            effective_to=None,
        )
        assert v.is_current(on_date=date(2026, 6, 1))


class TestCensusDecadalVintage(TestCase):

    def test_save_sets_kind_and_name_automatically(self):
        from socialwarehouse.geo.models import CensusDecadalVintage

        # 2010 was seeded by the migration; create 2040 for a fresh slot.
        v = CensusDecadalVintage.objects.create(
            decade=2040, effective_from=date(2040, 1, 1),
        )
        assert v.kind == "census-decadal"
        assert v.name == "2040"

    def test_parent_table_query_returns_decadal_rows(self):
        from socialwarehouse.geo.models import (
            CensusDecadalVintage, Vintage,
        )

        # Seeded 2010 and 2020 exist; verify parent-table query finds them.
        decadal_in_parent = Vintage.objects.filter(kind="census-decadal").count()
        decadal_count = CensusDecadalVintage.objects.count()
        assert decadal_in_parent == decadal_count


class TestACSVintage(TestCase):

    def test_5year_naming(self):
        from socialwarehouse.geo.models import ACSVintage

        # 2019-2023 was seeded by migration; create a hypothetical 2024-2028.
        v = ACSVintage.objects.create(
            start_year=2024, end_year=2028, span_years=ACSVintage.SPAN_5YEAR,
            effective_from=date(2029, 12, 1),
        )
        assert v.name == "2024-2028"
        assert v.kind == "acs"

    def test_1year_naming(self):
        from socialwarehouse.geo.models import ACSVintage

        v = ACSVintage.objects.create(
            start_year=2025, end_year=2025, span_years=ACSVintage.SPAN_1YEAR,
            effective_from=date(2026, 9, 1),
        )
        assert v.name == "2025"

    def test_unique_constraint(self):
        from django.db import IntegrityError
        from socialwarehouse.geo.models import ACSVintage

        ACSVintage.objects.create(
            start_year=2050, end_year=2054, span_years=ACSVintage.SPAN_5YEAR,
            effective_from=date(2055, 12, 1),
        )
        with self.assertRaises(IntegrityError):
            ACSVintage.objects.create(
                start_year=2050, end_year=2054, span_years=ACSVintage.SPAN_5YEAR,
                effective_from=date(2055, 12, 1),
            )


class TestBLSQCEWVintage(TestCase):

    def test_naming_quarter_format(self):
        from socialwarehouse.geo.models import BLSQCEWVintage

        v = BLSQCEWVintage.objects.create(
            year=2030, quarter=2, effective_from=date(2030, 4, 1),
        )
        assert v.name == "2030Q2"


class TestNCESSchoolYearVintage(TestCase):

    def test_naming_two_digit_end(self):
        from socialwarehouse.geo.models import NCESSchoolYearVintage

        v = NCESSchoolYearVintage.objects.create(
            start_year=2030, end_year=2031, effective_from=date(2030, 8, 1),
        )
        assert v.name == "2030-31"


class TestSeedKnownVintages(TestCase):

    def test_command_is_idempotent(self):
        from socialwarehouse.geo.models import Vintage

        # The migration ran seed_known_vintages already; rerunning must
        # not duplicate rows.
        before = Vintage.objects.count()
        call_command("seed_known_vintages", verbosity=0)
        after = Vintage.objects.count()
        assert before == after

    def test_dry_run_does_not_write(self):
        from socialwarehouse.geo.models import Vintage

        before = Vintage.objects.count()
        call_command("seed_known_vintages", "--dry-run", verbosity=0, stdout=StringIO())
        after = Vintage.objects.count()
        assert before == after

    def test_unknown_kind_reports_error(self):
        out = StringIO()
        err = StringIO()
        call_command(
            "seed_known_vintages", "--kinds=fictional-domain",
            stdout=out, stderr=err, verbosity=0,
        )
        assert "Unknown kinds" in out.getvalue() or "Unknown kinds" in err.getvalue()

    def test_seeded_catalog_includes_each_kind(self):
        from socialwarehouse.geo.models import (
            ACSVintage, BEARegionalVintage, BLSQCEWVintage,
            CensusDecadalVintage, NCESSchoolYearVintage,
        )

        assert CensusDecadalVintage.objects.count() >= 2
        assert ACSVintage.objects.count() >= 10
        assert BLSQCEWVintage.objects.count() >= 20
        assert BEARegionalVintage.objects.count() >= 10
        assert NCESSchoolYearVintage.objects.count() >= 10

    def test_latest_vintage_has_null_effective_to(self):
        """The most recent vintage of each kind is the 'unreplaced' one."""
        from socialwarehouse.geo.models import CensusDecadalVintage

        latest = CensusDecadalVintage.objects.order_by("-decade").first()
        assert latest is not None
        assert latest.effective_to is None
