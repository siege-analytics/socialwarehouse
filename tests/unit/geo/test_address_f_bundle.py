"""Regression tests for the address.py F-bundle: F4 + F5 + F6.

F4 (#93) + F5 (#94): populate_foreign_keys() does NOT call self.save().
F6 (#95): census_year default sourced from DEFAULT_CENSUS_YEAR module
constant (single edit site for the manual-per-decade bump).

Pure behavior tests — F4/F5 use a MagicMock instead of a real DB so the
test runs without DB fixtures; F6 reads the constant + field default
directly.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from socialwarehouse.geo.models import address as _addr_mod
from socialwarehouse.geo.models.address import Address, DEFAULT_CENSUS_YEAR


class TestF6CensusYearDefault(SimpleTestCase):

    def test_module_constant_is_2020(self):
        # Sentinel: if this constant changes without a coordinated update,
        # the test fires and surfaces the decade-bump moment.
        assert DEFAULT_CENSUS_YEAR == 2020

    def test_address_census_year_field_default_uses_constant(self):
        # The field default must be the constant itself — not a stale
        # literal that drifts when the constant is bumped.
        field = Address._meta.get_field("census_year")
        assert field.default == DEFAULT_CENSUS_YEAR

    def test_default_census_year_documented_in_source(self):
        # Soft check: the rationale comment should reference F6 / SW#95.
        src = Path(_addr_mod.__file__).read_text(encoding="utf-8")
        assert "DEFAULT_CENSUS_YEAR" in src
        assert "F6" in src or "SW#95" in src


class TestF4F5PopulateForeignKeysNoSave(SimpleTestCase):

    def test_populate_foreign_keys_does_not_call_save(self):
        # Build an Address-like instance but skip the DB write by
        # patching save. The method must not invoke save() internally.
        addr = Address(state_geoid="48", county_geoid="48201", census_year=2020)
        with patch.object(addr, "save") as save_mock, patch(
            "siege_utilities.geo.django.models.State"
        ) as State, patch(
            "siege_utilities.geo.django.models.County"
        ) as County, patch(
            "siege_utilities.geo.django.models.Tract"
        ), patch(
            "siege_utilities.geo.django.models.BlockGroup"
        ), patch(
            "siege_utilities.geo.django.models.CongressionalDistrict"
        ), patch(
            "siege_utilities.geo.django.models.VTD"
        ), patch(
            "siege_utilities.geo.django.models.StateLegislativeLower"
        ), patch(
            "siege_utilities.geo.django.models.StateLegislativeUpper"
        ):
            State.objects.filter.return_value.first.return_value = None
            County.objects.filter.return_value.first.return_value = None
            result = addr.populate_foreign_keys()
        save_mock.assert_not_called()
        # Returns self (Django ORM convention for chainable mutators).
        assert result is addr

    def test_source_has_no_self_save_inside_populate_foreign_keys(self):
        # writing-tests:6 carve-out — structural check that the body of
        # populate_foreign_keys does not contain self.save(). Comment/
        # docstring stripping per the codebase's existing pattern.
        src = Path(_addr_mod.__file__).read_text(encoding="utf-8")
        cleaned = re.sub(r'"""[\s\S]*?"""', "", src)
        cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
        cleaned = "\n".join(line.split("#", 1)[0] for line in cleaned.splitlines())

        # Slice out the body of populate_foreign_keys to scope the grep.
        match = re.search(
            r"def populate_foreign_keys\(self\):([\s\S]*?)(?=\n    def |\nclass |\Z)",
            cleaned,
        )
        assert match, "could not find populate_foreign_keys body in source"
        body = match.group(1)
        assert "self.save()" not in body, (
            "self.save() reintroduced into populate_foreign_keys — pre-F4 "
            "asymmetric-save behavior has returned"
        )
