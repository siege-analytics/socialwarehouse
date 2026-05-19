"""Sweep null=True off Address CharFields per Django convention (F3 / SW#92).

Pre-fix: 29 CharFields on Address used ``null=True, blank=True, default=None``.
Django convention for text fields is ``blank=True, default=""`` — NULL on
text columns creates a needless two-state representation (NULL vs ""),
forcing every filter site to know which case the data is in.

This migration is two phases inside one transaction (PostgreSQL wraps
migrations atomically by default):

1. **Data backfill**: ``UPDATE sw_geo_address SET <field> = '' WHERE
   <field> IS NULL`` for each of the 29 CharFields. Idempotent — re-run
   is a no-op on rows already converted.
2. **Schema change**: AlterField on each to drop ``null=True`` and set
   ``default=""``.

The data backfill MUST happen before the schema change. Order is preserved
by Django executing operations in list order.

Caller updates (in separate code changes, same PR):
- ``socialwarehouse/warehouse/services/geographic_enrichment.py`` —
  3 sites changed from ``tract_geoid__isnull=False`` to
  ``exclude(tract_geoid="")``. Post-migration, ``__isnull=False`` matches
  every row (column is NOT NULL); the new shape captures "has a tract
  assigned" correctly.
- ``tests/unit/geo/test_models.py:51`` — assertion changed from
  ``addr.tract_geoid is None`` to ``addr.tract_geoid == ""`` to match
  the new in-memory default.

Reverse migration: AlterField back to ``null=True``; the data backfill
is information-preserving (no way to distinguish post-fix "" from
pre-fix NULL, so no automatic re-null-ing on reverse).
"""

from django.db import migrations, models


# Names of the 29 CharFields swept by F3. Listed here so the data-
# backfill SQL and the AlterField ops share one source of truth.
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


# Pre-AlterField data backfill. Single SQL statement with all 29 UPDATEs.
# COALESCE is not used because we want explicit NULL→'' semantics, not
# coalesce-on-read. Each UPDATE is a no-op for rows that already have
# non-NULL values.
_BACKFILL_SQL = "\n".join(
    f"UPDATE sw_geo_address SET {field} = '' WHERE {field} IS NULL;"
    for field in _F3_FIELDS
)


# Field metadata for the AlterField ops. Most fields have a uniform shape;
# a few (geocode_source, geocode_quality, sldl_geoid, sldu_geoid) have
# help_text or choices and need to keep those.
_FIELD_METADATA = {
    # USPS address components
    "primary_number": {"max_length": 250},
    "street_name": {"max_length": 250},
    "street_suffix": {"max_length": 250},
    "city_name": {"max_length": 250},
    "default_city_name": {"max_length": 250},
    "state_abbreviation": {"max_length": 2},
    "zip5": {"max_length": 5},
    "delivery_point": {"max_length": 99},
    "delivery_point_check_digit": {"max_length": 99},
    # USPS / RDI classification
    "record_type": {"max_length": 250},
    "zip_type": {"max_length": 250},
    "county_fips": {"max_length": 250},
    "county_name": {"max_length": 250},
    "carrier_route": {"max_length": 250},
    "congressional_district": {"max_length": 250},
    "rdi": {"max_length": 250},
    "elot_sequence": {"max_length": 250},
    "elot_sort": {"max_length": 250},
    # Coordinate metadata
    "coordinate_license": {"max_length": 250},
    "precision": {"max_length": 250},
    "time_zone": {"max_length": 250},
    "utc_offset": {"max_length": 250},
    # Geocoding metadata
    "geocode_quality": {
        "max_length": 20,
        "help_text": "Quality: Rooftop, Interpolated, Approximate, Zip",
    },
    # Census unit GEOIDs
    "state_geoid": {"max_length": 2},
    "county_geoid": {"max_length": 5},
    "tract_geoid": {"max_length": 11},
    "block_group_geoid": {"max_length": 12},
    "block_geoid": {"max_length": 15},
    "vtd_geoid": {"max_length": 11},
    "cd_geoid": {"max_length": 4},
    "sldl_geoid": {
        "max_length": 5,
        "help_text": "State Legislative District Lower GEOID (state FIPS + district)",
    },
    "sldu_geoid": {
        "max_length": 5,
        "help_text": "State Legislative District Upper GEOID (state FIPS + district)",
    },
}


def _alter_field(name):
    """Build the post-F3 field metadata for AlterField op."""
    meta = _FIELD_METADATA[name]
    return models.CharField(
        blank=True,
        default="",
        **meta,
    )


class Migration(migrations.Migration):

    # geocode_source had choices added in 0002. The F3 sweep preserves
    # those choices and adds default="". The AlterField below uses the
    # full post-F3 shape for geocode_source explicitly.
    dependencies = [
        ("sw_geo", "0002_address_geocode_source_choices"),
    ]

    operations = [
        # ---- Phase 1: data backfill (NULL → '') ----
        migrations.RunSQL(
            sql=_BACKFILL_SQL,
            reverse_sql=migrations.RunSQL.noop,  # cannot distinguish post-fix '' from pre-fix NULL
        ),
        # ---- Phase 2: AlterField for each of the 29 fields ----
        *[
            migrations.AlterField(
                model_name="address",
                name=name,
                field=_alter_field(name),
            )
            for name in _F3_FIELDS
            if name != "geocode_source"  # handled separately below to preserve choices=
        ],
        # geocode_source: preserve the choices= added in 0002, add default=""
        migrations.AlterField(
            model_name="address",
            name="geocode_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("census", "Census Geocoder (US)"),
                    ("nominatim", "Nominatim (OpenStreetMap)"),
                    ("google", "Google Geocoding API"),
                    ("smartystreets", "SmartyStreets"),
                ],
                default="",
                help_text=(
                    "Source geocoder. Canonical values lowercase per "
                    "GEOCODE_SOURCE_CHOICES (F7 / SW#96). Existing rows "
                    "with non-canonical values (e.g. vendor-written "
                    "'Census') are preserved; only new admin-form "
                    "writes are constrained."
                ),
                max_length=50,
            ),
        ),
    ]
