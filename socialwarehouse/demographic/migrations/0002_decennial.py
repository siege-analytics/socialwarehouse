"""D Phase 3 (SW#192): DecennialVariable + DecennialCount.

Adds the PL 94-171 redistricting variable catalog and the long-format
count table. Seeds the curated PL catalog as part of the migration so
load_decennial can run immediately after migrate.
"""

from django.db import migrations, models


def _run_seed(apps, schema_editor):
    from django.core.management import call_command
    call_command("seed_decennial_variables", verbosity=0)


def _reverse_seed(apps, schema_editor):
    DecennialVariable = apps.get_model("sw_demographic", "DecennialVariable")
    DecennialVariable.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sw_demographic", "0001_initial"),
        ("sw_geo", "0007_c_medium_boundary_caches"),
    ]

    operations = [
        migrations.CreateModel(
            name="DecennialVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("variable_code", models.CharField(db_index=True, max_length=20, unique=True)),
                ("label", models.TextField()),
                ("concept", models.CharField(blank=True, default="", max_length=255)),
                ("table_code", models.CharField(db_index=True, max_length=20)),
                ("universe", models.CharField(blank=True, default="", max_length=255)),
                ("dataset", models.CharField(db_index=True, max_length=20)),
            ],
            options={
                "db_table": "sw_demographic_decennial_variable",
                "verbose_name": "Decennial Variable",
                "ordering": ["table_code", "variable_code"],
            },
        ),
        migrations.CreateModel(
            name="DecennialCount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=20)),
                ("value", models.BigIntegerField(blank=True, null=True)),
                ("annotation", models.CharField(blank=True, default="", max_length=10)),
                ("variable", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="counts",
                    to="sw_demographic.decennialvariable",
                )),
                ("vintage", models.ForeignKey(
                    limit_choices_to={"kind": "census-decadal"},
                    on_delete=models.deletion.CASCADE,
                    related_name="decennial_counts",
                    to="sw_geo.vintage",
                )),
            ],
            options={
                "db_table": "sw_demographic_decennial_count",
                "verbose_name": "Decennial Count",
                "unique_together": {("vintage", "variable", "boundary_type", "geoid")},
                "indexes": [
                    models.Index(fields=["boundary_type", "geoid", "vintage"],
                                 name="sw_dem_dec_bnd_geo_vnt_idx"),
                    models.Index(fields=["variable", "vintage", "boundary_type"],
                                 name="sw_dem_dec_var_vnt_bnd_idx"),
                ],
            },
        ),
        migrations.RunPython(_run_seed, _reverse_seed),
    ]
