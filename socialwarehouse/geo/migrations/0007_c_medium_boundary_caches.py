"""Template-readiness C medium-priority batch (SW#191): add cache fields
for PUMA, UrbanArea, and the 7 per-kind special-district types on
Address and AddressBoundaryPeriod.

Additive only. The boundary models themselves are tracked upstream
in SU#535 (UrbanArea already exists; PUMA + 7 special-district kinds
to be added). These caches don't depend on SU shipping; the geoid
strings populate once assign_boundaries is updated post-SU.

After this migration, `Address._BOUNDARY_TYPES` includes 9 more
types so F11 helpers cover them automatically.
"""

from django.db import migrations, models


_NEW_TYPES = [
    ("puma_geoid", 7),
    ("urban_area_geoid", 5),
    ("fire_district_geoid", 10),
    ("water_district_geoid", 10),
    ("hospital_district_geoid", 10),
    ("library_district_geoid", 10),
    ("cemetery_district_geoid", 10),
    ("mosquito_district_geoid", 10),
    ("other_special_district_geoid", 10),
]


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0006_c_high_priority_boundary_caches"),
    ]

    operations = [
        # Address: blank-default CharFields.
        *[
            migrations.AddField(
                model_name="address",
                name=field_name,
                field=models.CharField(blank=True, default="", max_length=max_len),
            )
            for (field_name, max_len) in _NEW_TYPES
        ],
        # AddressBoundaryPeriod: nullable CharFields (matches existing ABP convention).
        *[
            migrations.AddField(
                model_name="addressboundaryperiod",
                name=field_name,
                field=models.CharField(blank=True, max_length=max_len, null=True),
            )
            for (field_name, max_len) in _NEW_TYPES
        ],
    ]
