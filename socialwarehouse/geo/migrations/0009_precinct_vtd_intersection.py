from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0008_irs_soi_vintage"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrecinctVTDIntersection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("precinct_geoid", models.CharField(db_index=True, max_length=20)),
                ("vtd_geoid", models.CharField(db_index=True, max_length=11)),
                ("election_cycle", models.PositiveSmallIntegerField(db_index=True)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("overlap_area_sqm", models.BigIntegerField(blank=True, help_text="Area of intersection in square meters", null=True)),
                ("overlap_fraction", models.DecimalField(blank=True, decimal_places=4, help_text="Fraction of precinct area that overlaps with VTD (0.0-1.0)", max_digits=5, null=True)),
                ("is_dominant", models.BooleanField(db_index=True, default=False, help_text="True if >50% of precinct area is in this VTD")),
                ("computed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Precinct-VTD Intersection",
                "verbose_name_plural": "Precinct-VTD Intersections",
                "db_table": "sw_geo_intersection_precinct_vtd",
                "ordering": ["precinct_geoid", "-overlap_fraction"],
                "unique_together": {("precinct_geoid", "vtd_geoid", "election_cycle")},
            },
        ),
        migrations.AddIndex(
            model_name="precinctvtdintersection",
            index=models.Index(fields=["election_cycle", "precinct_geoid"], name="idx_pvtd_cycle_precinct"),
        ),
        migrations.AddIndex(
            model_name="precinctvtdintersection",
            index=models.Index(fields=["election_cycle", "vtd_geoid"], name="idx_pvtd_cycle_vtd"),
        ),
        migrations.AddIndex(
            model_name="precinctvtdintersection",
            index=models.Index(fields=["state", "election_cycle"], name="idx_pvtd_state_cycle"),
        ),
    ]
