"""SW#305: add tribal_area_geoid and county_subdivision_geoid cache fields
on Address and AddressBoundaryPeriod.

Upstream siege_utilities models (TribalArea, CountySubdivision) were added
in SU PR #553. These cache fields mirror the upstream geoid convention
(max_length=20, matching CensusTIGERBoundary.geoid).
"""

from django.db import migrations, models


_NEW_TYPES = [
    ("tribal_area_geoid", 20),
    ("county_subdivision_geoid", 20),
]


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0009_precinct_vtd_intersection"),
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
