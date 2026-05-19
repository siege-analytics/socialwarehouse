"""Regression test for F7 (SW#96): Address.geocode_source has choices=
keyed to the GEOCODE_SOURCE_CHOICES module constant.

Behavior tests — read the model field metadata directly.
"""

from django.test import SimpleTestCase

from socialwarehouse.geo.models.address import Address, GEOCODE_SOURCE_CHOICES


class TestF7GeocodeSourceChoices(SimpleTestCase):

    def test_module_constant_has_expected_canonical_values(self):
        # Sentinel: a change to this set requires updating the migration
        # AND any downstream callers that rely on these values.
        values = {value for value, _label in GEOCODE_SOURCE_CHOICES}
        assert values == {"census", "nominatim", "google", "smartystreets"}

    def test_module_constant_values_are_lowercase(self):
        # The canonical is lowercase to match SW's own writers in
        # geocode_addresses.py (addr.geocode_source = "census" / "nominatim").
        for value, _label in GEOCODE_SOURCE_CHOICES:
            assert value == value.lower(), (
                f"GEOCODE_SOURCE_CHOICES value {value!r} is not lowercase; "
                "this breaks SW writer compatibility"
            )

    def test_field_choices_sourced_from_module_constant(self):
        # The field default must reference the constant, not duplicate it
        # as a literal — duplicating invites drift.
        field = Address._meta.get_field("geocode_source")
        assert field.choices == tuple(GEOCODE_SOURCE_CHOICES) or list(field.choices) == list(GEOCODE_SOURCE_CHOICES)

    def test_field_is_not_nullable_post_f3(self):
        # F7 (this PR) preserved nullable. F3 / SW#92 tightened the field
        # to NOT NULL with default="" (Django convention). After F3 the
        # field's null attribute is False; existing NULL rows were
        # backfilled to "" in migration 0003 before the schema change.
        field = Address._meta.get_field("geocode_source")
        assert field.null is False
        assert field.blank is True
        assert field.default == ""
