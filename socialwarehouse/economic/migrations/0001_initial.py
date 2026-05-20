"""Template-readiness E Phase 1 (SW#193): BLSQCEWAggregate model.

Per E Q1 = (a) 2-digit NAICS default, Q4 = (a) files-only path.
Vintage FK targets the polymorphic Vintage parent with
limit_choices_to={"kind": "bls-qcew"}; BLSQCEWVintage rows for the
2010Q1-2024Q4 catalog are seeded by sw_geo migration 0004.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_geo", "0006_c_high_priority_boundary_caches"),
    ]

    operations = [
        migrations.CreateModel(
            name="BLSQCEWAggregate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=20)),
                ("ownership_code", models.CharField(
                    choices=[
                        ("0", "Total Covered"),
                        ("1", "Federal Government"),
                        ("2", "State Government"),
                        ("3", "Local Government"),
                        ("5", "Private"),
                        ("8", "Total Government"),
                        ("9", "Total UI Covered"),
                    ],
                    db_index=True, max_length=2,
                )),
                ("industry_code", models.CharField(db_index=True, max_length=10)),
                ("avg_monthly_employment", models.PositiveIntegerField(blank=True, null=True)),
                ("total_quarterly_wages", models.BigIntegerField(blank=True, null=True)),
                ("avg_weekly_wage", models.PositiveIntegerField(blank=True, null=True)),
                ("establishment_count", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "vintage",
                    models.ForeignKey(
                        limit_choices_to={"kind": "bls-qcew"},
                        on_delete=models.CASCADE,
                        related_name="bls_qcew_aggregates",
                        to="sw_geo.vintage",
                    ),
                ),
            ],
            options={
                "db_table": "sw_economic_bls_qcew_aggregate",
                "verbose_name": "BLS QCEW Aggregate",
                "unique_together": {
                    ("vintage", "boundary_type", "geoid", "ownership_code", "industry_code"),
                },
            },
        ),
        migrations.AddIndex(
            model_name="blsqcewaggregate",
            index=models.Index(fields=["boundary_type", "geoid", "vintage"], name="sw_econ_qcew_bgv_idx"),
        ),
        migrations.AddIndex(
            model_name="blsqcewaggregate",
            index=models.Index(fields=["vintage", "industry_code"], name="sw_econ_qcew_vi_idx"),
        ),
    ]
