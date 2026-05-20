"""Create the polymorphic Vintage parent + per-kind subclass tables.

Template-readiness B PR #1 (SW#190): additive only. ABP's existing FK
to CensusVintageConfig is NOT touched in this migration; B PR #2
retargets ABP and drops CensusVintageConfig.

After this migration runs, the Vintage tables exist but are unused by
ABP. A data-migration step at the end runs the seed_known_vintages
command to pre-populate the standard catalogs across census-decadal,
ACS, BLS QCEW, BEA regional, and NCES school year. Redistricting-plan
vintages are seeded on demand by assign_boundaries.
"""

from django.db import migrations, models


def _run_seed_known_vintages(apps, schema_editor):
    """Data-migration step that runs seed_known_vintages."""
    from django.core.management import call_command
    call_command("seed_known_vintages", verbosity=0)


def _reverse_seed(apps, schema_editor):
    """Reverse: delete every Vintage row this migration's seed created.
    Safe because the subclass tables are dropped by the schema reverse
    anyway; this is here to make the migration explicitly reversible.
    """
    Vintage = apps.get_model("sw_geo", "Vintage")
    Vintage.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0003_address_charfield_null_to_blank_default"),
    ]

    operations = [
        # Parent table.
        migrations.CreateModel(
            name="Vintage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(db_index=True, max_length=100)),
                ("kind", models.CharField(
                    choices=[
                        ("census-decadal", "Decennial Census"),
                        ("acs", "American Community Survey"),
                        ("bls-qcew", "BLS Quarterly Census of Employment and Wages"),
                        ("bea-regional", "BEA Regional"),
                        ("nces-school-year", "NCES School Year"),
                        ("redistricting-plan", "Redistricting Plan"),
                    ],
                    db_index=True, max_length=30,
                )),
                ("effective_from", models.DateField(db_index=True)),
                ("effective_to", models.DateField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "sw_geo_vintage",
                "ordering": ["kind", "-effective_from"],
            },
        ),
        migrations.AddIndex(
            model_name="vintage",
            index=models.Index(fields=["kind", "effective_to"], name="sw_geo_vint_kind_effto_idx"),
        ),
        migrations.AddIndex(
            model_name="vintage",
            index=models.Index(fields=["effective_from", "effective_to"], name="sw_geo_vint_effrange_idx"),
        ),

        # Subclass tables (multi-table inheritance: each has a 1:1 FK to parent).
        migrations.CreateModel(
            name="CensusDecadalVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.CASCADE, parent_link=True,
                    primary_key=True, serialize=False, to="sw_geo.vintage",
                )),
                ("decade", models.PositiveSmallIntegerField(unique=True)),
            ],
            options={
                "db_table": "sw_geo_vintage_census_decadal",
                "verbose_name": "Census Decadal Vintage",
            },
            bases=("sw_geo.vintage",),
        ),
        migrations.CreateModel(
            name="ACSVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.CASCADE, parent_link=True,
                    primary_key=True, serialize=False, to="sw_geo.vintage",
                )),
                ("start_year", models.PositiveSmallIntegerField()),
                ("end_year", models.PositiveSmallIntegerField()),
                ("span_years", models.PositiveSmallIntegerField(
                    choices=[(1, "1-year"), (5, "5-year")],
                )),
            ],
            options={
                "db_table": "sw_geo_vintage_acs",
                "verbose_name": "ACS Vintage",
                "unique_together": {("start_year", "end_year", "span_years")},
            },
            bases=("sw_geo.vintage",),
        ),
        migrations.CreateModel(
            name="BLSQCEWVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.CASCADE, parent_link=True,
                    primary_key=True, serialize=False, to="sw_geo.vintage",
                )),
                ("year", models.PositiveSmallIntegerField()),
                ("quarter", models.PositiveSmallIntegerField(
                    choices=[(1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4")],
                )),
            ],
            options={
                "db_table": "sw_geo_vintage_bls_qcew",
                "verbose_name": "BLS QCEW Vintage",
                "unique_together": {("year", "quarter")},
            },
            bases=("sw_geo.vintage",),
        ),
        migrations.CreateModel(
            name="BEARegionalVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.CASCADE, parent_link=True,
                    primary_key=True, serialize=False, to="sw_geo.vintage",
                )),
                ("year", models.PositiveSmallIntegerField(unique=True)),
            ],
            options={
                "db_table": "sw_geo_vintage_bea_regional",
                "verbose_name": "BEA Regional Vintage",
            },
            bases=("sw_geo.vintage",),
        ),
        migrations.CreateModel(
            name="NCESSchoolYearVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.CASCADE, parent_link=True,
                    primary_key=True, serialize=False, to="sw_geo.vintage",
                )),
                ("start_year", models.PositiveSmallIntegerField()),
                ("end_year", models.PositiveSmallIntegerField()),
            ],
            options={
                "db_table": "sw_geo_vintage_nces_school_year",
                "verbose_name": "NCES School Year Vintage",
                "unique_together": {("start_year", "end_year")},
            },
            bases=("sw_geo.vintage",),
        ),
        migrations.CreateModel(
            name="RedistrictingPlanVintage",
            fields=[
                ("vintage_ptr", models.OneToOneField(
                    auto_created=True, on_delete=models.CASCADE, parent_link=True,
                    primary_key=True, serialize=False, to="sw_geo.vintage",
                )),
                ("siege_redistricting_plan_id", models.PositiveBigIntegerField(unique=True)),
                ("state_fips", models.CharField(db_index=True, max_length=2)),
                ("chamber", models.CharField(db_index=True, max_length=20)),
                ("plan_name", models.CharField(max_length=255)),
            ],
            options={
                "db_table": "sw_geo_vintage_redistricting_plan",
                "verbose_name": "Redistricting Plan Vintage",
            },
            bases=("sw_geo.vintage",),
        ),

        # Seed the standard catalogs (census-decadal / ACS / BLS QCEW / BEA / NCES).
        migrations.RunPython(_run_seed_known_vintages, _reverse_seed),
    ]
