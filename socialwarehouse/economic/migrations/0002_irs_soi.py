"""E Phase 3 (SW#193): IRSSOIIncomeBucket + IRSSOIAggregate.

Adds per-vintage AGI bucket table + the long-format ZCTA aggregate.
Depends on sw_geo 0008 (IRSSOIVintage subclass + irs-soi kind).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_economic", "0001_initial"),
        ("sw_geo", "0008_irs_soi_vintage"),
    ]

    operations = [
        migrations.CreateModel(
            name="IRSSOIIncomeBucket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("bucket_code", models.PositiveSmallIntegerField()),
                ("label", models.CharField(max_length=80)),
                ("lower_bound", models.BigIntegerField(blank=True, null=True)),
                ("upper_bound", models.BigIntegerField(blank=True, null=True)),
                ("vintage", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="irs_soi_buckets",
                    limit_choices_to={"kind": "irs-soi"},
                    to="sw_geo.vintage",
                )),
            ],
            options={
                "db_table": "sw_economic_irs_soi_bucket",
                "verbose_name": "IRS SOI Income Bucket",
                "unique_together": {("vintage", "bucket_code")},
                "ordering": ["vintage", "bucket_code"],
            },
        ),
        migrations.CreateModel(
            name="IRSSOIAggregate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, default="zcta", max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=20)),
                ("return_count", models.BigIntegerField(blank=True, null=True)),
                ("exemption_count", models.BigIntegerField(blank=True, null=True)),
                ("agi_total", models.BigIntegerField(blank=True, null=True)),
                ("taxable_income_total", models.BigIntegerField(blank=True, null=True)),
                ("total_tax_total", models.BigIntegerField(blank=True, null=True)),
                ("agi_bin", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="aggregates",
                    to="sw_economic.irssoiincomebucket",
                )),
                ("vintage", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="irs_soi_aggregates",
                    limit_choices_to={"kind": "irs-soi"},
                    to="sw_geo.vintage",
                )),
            ],
            options={
                "db_table": "sw_economic_irs_soi_aggregate",
                "verbose_name": "IRS SOI Aggregate",
                "unique_together": {("vintage", "boundary_type", "geoid", "agi_bin")},
                "indexes": [
                    models.Index(fields=["boundary_type", "geoid", "vintage"],
                                 name="sw_eco_soi_bnd_geo_vnt_idx"),
                    models.Index(fields=["vintage", "agi_bin"],
                                 name="sw_eco_soi_vnt_bin_idx"),
                ],
            },
        ),
    ]
