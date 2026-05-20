"""Template-readiness F Phase 1a (SW#194): NCESDistrictAggregate.

Per F design: Q1 = (b) CCD + EDGE; Q2 = (b) district + school level;
Q4 = (b) all line items. This migration covers the district half of
the CCD ingest (Phase 1a). Phase 1b adds school-level; Phase 1c adds
EDGE demographics per district.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_geo", "0006_c_high_priority_boundary_caches"),
    ]

    operations = [
        migrations.CreateModel(
            name="NCESDistrictAggregate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, default="school_district", max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=7)),
                ("district_type", models.CharField(
                    blank=True, default="", max_length=20,
                    choices=[
                        ("unified", "Unified (K-12)"),
                        ("elementary", "Elementary only"),
                        ("secondary", "Secondary only"),
                        ("other", "Other (charter, special, supervisory union)"),
                    ],
                )),
                ("state_fips", models.CharField(blank=True, db_index=True, default="", max_length=2)),
                ("enrollment_total", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_pk_grade_k", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_grade_1_5", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_grade_6_8", models.PositiveIntegerField(blank=True, null=True)),
                ("enrollment_grade_9_12", models.PositiveIntegerField(blank=True, null=True)),
                ("free_lunch_eligible_count", models.PositiveIntegerField(blank=True, null=True)),
                ("reduced_lunch_eligible_count", models.PositiveIntegerField(blank=True, null=True)),
                ("title_i_eligible", models.BooleanField(blank=True, null=True)),
                ("teachers_fte", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("instructional_aides_fte", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("administrators_fte", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("instructional_coordinators_fte", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("support_staff_fte", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("revenue_total", models.BigIntegerField(blank=True, null=True)),
                ("revenue_federal", models.BigIntegerField(blank=True, null=True)),
                ("revenue_federal_title_i", models.BigIntegerField(blank=True, null=True)),
                ("revenue_federal_idea", models.BigIntegerField(blank=True, null=True)),
                ("revenue_federal_child_nutrition", models.BigIntegerField(blank=True, null=True)),
                ("revenue_state", models.BigIntegerField(blank=True, null=True)),
                ("revenue_state_formula", models.BigIntegerField(blank=True, null=True)),
                ("revenue_state_compensatory", models.BigIntegerField(blank=True, null=True)),
                ("revenue_state_special_ed", models.BigIntegerField(blank=True, null=True)),
                ("revenue_local", models.BigIntegerField(blank=True, null=True)),
                ("revenue_local_property_tax", models.BigIntegerField(blank=True, null=True)),
                ("revenue_local_parent_govt", models.BigIntegerField(blank=True, null=True)),
                ("expenditure_total", models.BigIntegerField(blank=True, null=True)),
                ("expenditure_instruction", models.BigIntegerField(blank=True, null=True)),
                ("expenditure_support_services", models.BigIntegerField(blank=True, null=True)),
                ("expenditure_food_services", models.BigIntegerField(blank=True, null=True)),
                ("expenditure_capital_outlay", models.BigIntegerField(blank=True, null=True)),
                ("expenditure_per_pupil", models.PositiveIntegerField(blank=True, null=True)),
                ("long_term_debt_outstanding", models.BigIntegerField(blank=True, null=True)),
                (
                    "vintage",
                    models.ForeignKey(
                        limit_choices_to={"kind": "nces-school-year"},
                        on_delete=models.CASCADE,
                        related_name="nces_district_aggregates",
                        to="sw_geo.vintage",
                    ),
                ),
            ],
            options={
                "db_table": "sw_civic_nces_district_aggregate",
                "verbose_name": "NCES District Aggregate",
                "unique_together": {("vintage", "geoid")},
            },
        ),
        migrations.AddIndex(
            model_name="ncesdistrictaggregate",
            index=models.Index(fields=["boundary_type", "geoid", "vintage"], name="sw_civic_nces_bgv_idx"),
        ),
        migrations.AddIndex(
            model_name="ncesdistrictaggregate",
            index=models.Index(fields=["state_fips", "vintage"], name="sw_civic_nces_sv_idx"),
        ),
    ]
