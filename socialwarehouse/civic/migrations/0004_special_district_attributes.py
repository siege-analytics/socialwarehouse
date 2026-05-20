"""F Phase 2 (SW#194): SpecialDistrictAttributes — COG-style attributes.

Per maintainer's call (2026-05-20 thread): ship the warehouse-side
schema; defer auto-ingest. The FEC analysis project (or any custom
loader) writes against this table directly.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_civic", "0003_nces_edge_demographics"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpecialDistrictAttributes",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(
                    choices=[
                        ("fire_district", "fire_district"),
                        ("water_district", "water_district"),
                        ("hospital_district", "hospital_district"),
                        ("library_district", "library_district"),
                        ("cemetery_district", "cemetery_district"),
                        ("mosquito_district", "mosquito_district"),
                        ("other_special_district", "other_special_district"),
                    ],
                    db_index=True, max_length=30,
                )),
                ("geoid", models.CharField(db_index=True, max_length=20)),
                ("source_year", models.PositiveSmallIntegerField(db_index=True)),
                ("function", models.CharField(blank=True, default="", max_length=80)),
                ("governing_body", models.CharField(blank=True, default="", max_length=255)),
                ("annual_revenue", models.BigIntegerField(blank=True, null=True)),
                ("source_url", models.URLField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "sw_civic_special_district_attributes",
                "verbose_name": "Special District Attributes",
                "verbose_name_plural": "Special District Attributes",
                "unique_together": {("boundary_type", "geoid", "source_year")},
                "indexes": [
                    models.Index(fields=["boundary_type", "source_year"],
                                 name="sw_civ_spdist_bnd_yr_idx"),
                ],
                "ordering": ["boundary_type", "geoid", "source_year"],
            },
        ),
    ]
