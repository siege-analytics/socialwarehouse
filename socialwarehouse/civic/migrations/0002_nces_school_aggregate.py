"""F Phase 1b (SW#194): NCESSchoolAggregate for per-school NCES data."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_civic", "0001_initial"),
        ("sw_geo", "0006_c_high_priority_boundary_caches"),
    ]

    operations = [
        migrations.CreateModel(
            name="NCESSchoolAggregate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, default="school", max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=12)),
                ("leaid", models.CharField(db_index=True, max_length=7)),
                ("state_fips", models.CharField(blank=True, db_index=True, default="", max_length=2)),
                ("school_name", models.CharField(blank=True, default="", max_length=255)),
                ("school_type", models.CharField(
                    blank=True, default="", max_length=20,
                    choices=[
                        ("regular", "Regular school"),
                        ("special", "Special education school"),
                        ("vocational", "Vocational school"),
                        ("alternative", "Alternative school"),
                        ("other", "Other"),
                    ],
                )),
                ("school_status", models.CharField(
                    blank=True, default="", max_length=20,
                    choices=[
                        ("open", "Open"),
                        ("closed", "Closed"),
                        ("new", "New school"),
                        ("added", "Added to NCES universe"),
                        ("changed_boundary", "Boundary change"),
                        ("inactive", "Inactive"),
                        ("future", "Future open date"),
                        ("reopened", "Reopened"),
                    ],
                )),
                ("is_charter", models.BooleanField(blank=True, null=True)),
                ("is_magnet", models.BooleanField(blank=True, null=True)),
                ("is_title_i", models.BooleanField(blank=True, null=True)),
                ("grade_low", models.CharField(blank=True, default="", max_length=4)),
                ("grade_high", models.CharField(blank=True, default="", max_length=4)),
                ("enrollment_total", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_pk_grade_k", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_grade_1_5", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_grade_6_8", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_grade_9_12", models.PositiveIntegerField(blank=True, null=True)),
                ("free_lunch_eligible_count", models.PositiveIntegerField(blank=True, null=True)),
                ("reduced_lunch_eligible_count", models.PositiveIntegerField(blank=True, null=True)),
                ("teachers_fte", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                (
                    "vintage",
                    models.ForeignKey(
                        limit_choices_to={"kind": "nces-school-year"},
                        on_delete=models.CASCADE,
                        related_name="nces_school_aggregates",
                        to="sw_geo.vintage",
                    ),
                ),
            ],
            options={
                "db_table": "sw_civic_nces_school_aggregate",
                "verbose_name": "NCES School Aggregate",
                "unique_together": {("vintage", "geoid")},
            },
        ),
        migrations.AddIndex(
            model_name="ncesschoolaggregate",
            index=models.Index(fields=["boundary_type", "geoid", "vintage"], name="sw_civic_sch_bgv_idx"),
        ),
        migrations.AddIndex(
            model_name="ncesschoolaggregate",
            index=models.Index(fields=["leaid", "vintage"], name="sw_civic_sch_lea_idx"),
        ),
        migrations.AddIndex(
            model_name="ncesschoolaggregate",
            index=models.Index(fields=["state_fips", "vintage"], name="sw_civic_sch_sv_idx"),
        ),
    ]
