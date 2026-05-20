"""Add IRSSOIVintage subclass + irs-soi to KIND_CHOICES.

Per E Phase 3 (SW#193) / E Q2 = (b) new vintage kind. Mirrors the
BEARegionalVintage shape (annual, integer year) with `tax_year`
instead of `year` so the column name is unambiguous in joins.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0007_c_medium_boundary_caches"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vintage",
            name="kind",
            field=models.CharField(
                choices=[
                    ("census-decadal", "Decennial Census"),
                    ("acs", "American Community Survey"),
                    ("bls-qcew", "BLS Quarterly Census of Employment and Wages"),
                    ("bea-regional", "BEA Regional"),
                    ("nces-school-year", "NCES School Year"),
                    ("redistricting-plan", "Redistricting Plan"),
                    ("irs-soi", "IRS SOI Individual Income Tax Statistics"),
                ],
                db_index=True, max_length=30,
                help_text=(
                    "Discriminator. Set automatically by each subclass's save() "
                    "method; downstream code can filter by kind without downcasting."
                ),
            ),
        ),
        migrations.CreateModel(
            name="IRSSOIVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.deletion.CASCADE,
                    parent_link=True, primary_key=True, serialize=False,
                    to="sw_geo.vintage",
                )),
                ("tax_year", models.PositiveSmallIntegerField(unique=True)),
            ],
            options={
                "db_table": "sw_geo_vintage_irs_soi",
                "verbose_name": "IRS SOI Vintage",
            },
            bases=("sw_geo.vintage",),
        ),
    ]
