"""Add choices= to Address.geocode_source (F7 / SW#96).

Metadata-only change: choices add does not validate existing rows;
only admin-form writes for new/edited rows enforce the choice set.
Existing rows with non-canonical values (legacy data) are preserved
unchanged.

The choices canonical-set lives in
``socialwarehouse.geo.models.address.GEOCODE_SOURCE_CHOICES``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0001_initial"),
    ]

    operations = [
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
                help_text=(
                    "Source geocoder. Canonical values lowercase per "
                    "GEOCODE_SOURCE_CHOICES (F7 / SW#96). Existing rows "
                    "with non-canonical values (e.g. vendor-written "
                    "'Census') are preserved; only new admin-form "
                    "writes are constrained."
                ),
                max_length=50,
                null=True,
            ),
        ),
    ]
