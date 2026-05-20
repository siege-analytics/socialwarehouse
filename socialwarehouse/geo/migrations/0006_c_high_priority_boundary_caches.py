"""Template-readiness C high-priority batch (SW#191): add cache fields
for the four new boundary types — ZCTA, Place, CBSA, SchoolDistrict —
on Address and AddressBoundaryPeriod.

Additive only. The boundary models themselves live upstream in
siege_utilities (tracked SU#532); these are pure string caches keyed
by the same `{type}_geoid` convention as the existing nine types.

After this migration, `Address._BOUNDARY_TYPES` includes the four new
types, so F11 helpers (`boundary_history`, `boundary_on`,
`boundary_timeline`, etc.) automatically cover them. Field values
remain empty until SU#532 ships and `assign_boundaries` is updated to
populate them.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0005_template_b_cutover"),
    ]

    operations = [
        # Address cache fields.
        migrations.AddField(
            model_name="address",
            name="zcta_geoid",
            field=models.CharField(blank=True, default="", max_length=5),
        ),
        migrations.AddField(
            model_name="address",
            name="place_geoid",
            field=models.CharField(blank=True, default="", max_length=7),
        ),
        migrations.AddField(
            model_name="address",
            name="cbsa_geoid",
            field=models.CharField(blank=True, default="", max_length=5),
        ),
        migrations.AddField(
            model_name="address",
            name="school_district_geoid",
            field=models.CharField(blank=True, default="", max_length=7),
        ),
        # AddressBoundaryPeriod cache fields.
        migrations.AddField(
            model_name="addressboundaryperiod",
            name="zcta_geoid",
            field=models.CharField(blank=True, max_length=5, null=True),
        ),
        migrations.AddField(
            model_name="addressboundaryperiod",
            name="place_geoid",
            field=models.CharField(blank=True, max_length=7, null=True),
        ),
        migrations.AddField(
            model_name="addressboundaryperiod",
            name="cbsa_geoid",
            field=models.CharField(blank=True, max_length=5, null=True),
        ),
        migrations.AddField(
            model_name="addressboundaryperiod",
            name="school_district_geoid",
            field=models.CharField(blank=True, max_length=7, null=True),
        ),
    ]
