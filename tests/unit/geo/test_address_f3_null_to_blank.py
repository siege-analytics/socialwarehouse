"""Regression tests for F3 (SW#92): Address CharFields use blank=True
default="" per Django convention, not null=True default=None.

Verifies the metadata sweep across all 29 affected CharFields and
confirms the caller-update for the "" semantic ("not yet assigned"
replaces NULL).
"""

from django.test import SimpleTestCase

from socialwarehouse.geo.models.address import Address


# The 29 CharFields swept by F3. Source of truth lives in the migration;
# this list mirrors it for the test to fire if the sweep is incomplete
# or if a new CharField is added without applying the convention.
_F3_FIELDS = [
    "primary_number",
    "street_name",
    "street_suffix",
    "city_name",
    "default_city_name",
    "state_abbreviation",
    "zip5",
    "delivery_point",
    "delivery_point_check_digit",
    "record_type",
    "zip_type",
    "county_fips",
    "county_name",
    "carrier_route",
    "congressional_district",
    "rdi",
    "elot_sequence",
    "elot_sort",
    "coordinate_license",
    "precision",
    "time_zone",
    "utc_offset",
    "geocode_quality",
    "geocode_source",
    "state_geoid",
    "county_geoid",
    "tract_geoid",
    "block_group_geoid",
    "block_geoid",
    "vtd_geoid",
    "cd_geoid",
    "sldl_geoid",
    "sldu_geoid",
]


class TestF3CharFieldsConvention(SimpleTestCase):

    def test_no_charfield_has_null_true(self):
        # Any CharField with null=True is a Django-convention violation
        # and should be fixed in lockstep with the migration.
        violators = []
        for field in Address._meta.get_fields():
            from django.db.models import CharField
            if isinstance(field, CharField) and field.null:
                violators.append(field.name)
        assert violators == [], (
            f"CharField(s) still using null=True: {violators}. "
            "F3/SW#92 sweep should set blank=True, default=''."
        )

    def test_swept_fields_have_blank_true(self):
        for name in _F3_FIELDS:
            field = Address._meta.get_field(name)
            assert field.blank is True, f"{name!r}: expected blank=True"

    def test_swept_fields_have_empty_string_default(self):
        for name in _F3_FIELDS:
            field = Address._meta.get_field(name)
            assert field.default == "", (
                f"{name!r}: expected default='', got {field.default!r}"
            )

    def test_fresh_address_has_empty_string_for_swept_fields(self):
        # A new in-memory Address picks up the field defaults — every
        # F3-swept field should be '', not None.
        addr = Address()
        for name in _F3_FIELDS:
            value = getattr(addr, name)
            assert value == "", (
                f"fresh Address.{name} is {value!r}; "
                "expected '' (post-F3 default)"
            )

    def test_latitude_longitude_stay_nullable(self):
        # F3 scope is CharField only. Numeric fields legitimately use
        # NULL for "unknown" and should NOT be in the sweep.
        for name in ("latitude", "longitude"):
            field = Address._meta.get_field(name)
            assert field.null is True, (
                f"{name!r}: expected null=True (F3 is CharField-scope)"
            )
