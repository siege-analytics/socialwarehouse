"""F Phase 1c (SW#194): NCESDistrictEDGEDemographics — per-district ACS-derived estimates."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_civic", "0002_nces_school_aggregate"),
        ("sw_geo", "0006_c_high_priority_boundary_caches"),
    ]

    operations = [
        migrations.CreateModel(
            name="NCESDistrictEDGEDemographics",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, default="school_district", max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=7)),
                ("state_fips", models.CharField(blank=True, db_index=True, default="", max_length=2)),
                ("source_acs_endpoint", models.CharField(blank=True, default="", max_length=20)),
                ("total_population", models.PositiveIntegerField(blank=True, null=True)),
                ("population_5_17", models.PositiveIntegerField(blank=True, null=True)),
                ("population_under_5", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_white_nh", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_black_nh", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_asian_nh", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_aian_nh", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_nhpi_nh", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_two_or_more_nh", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_hispanic", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_in_poverty", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_poverty_rate", models.DecimalField(blank=True, decimal_places=4, max_digits=6, null=True)),
                ("households_total", models.PositiveIntegerField(blank=True, null=True)),
                ("households_with_school_age", models.PositiveIntegerField(blank=True, null=True)),
                ("median_household_income", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_english_at_home", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_other_lang_at_home", models.PositiveIntegerField(blank=True, null=True)),
                ("pop_5_17_foreign_born", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "vintage",
                    models.ForeignKey(
                        limit_choices_to={"kind": "nces-school-year"},
                        on_delete=models.CASCADE,
                        related_name="nces_edge_demographics",
                        to="sw_geo.vintage",
                    ),
                ),
            ],
            options={
                "db_table": "sw_civic_nces_edge_demographics",
                "verbose_name": "NCES EDGE District Demographics",
                "unique_together": {("vintage", "geoid")},
            },
        ),
        migrations.AddIndex(
            model_name="ncesdistrictedgedemographics",
            index=models.Index(fields=["boundary_type", "geoid", "vintage"], name="sw_civic_edge_bgv_idx"),
        ),
        migrations.AddIndex(
            model_name="ncesdistrictedgedemographics",
            index=models.Index(fields=["state_fips", "vintage"], name="sw_civic_edge_sv_idx"),
        ),
    ]
