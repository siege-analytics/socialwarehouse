"""Template-readiness D Phase 1a (SW#192): ACSVariable + ACSEstimate
model surface. Additive new app `sw_demographic`.

After this migration, the variable catalog is seeded with the small
curated Phase 1a subset; the load_acs command (Phase 1b) writes
ACSEstimate rows that reference these variables.
"""

from django.db import migrations, models


def _run_seed_acs_variables(apps, schema_editor):
    from django.core.management import call_command
    call_command("seed_acs_variables", verbosity=0)


def _reverse_seed(apps, schema_editor):
    ACSVariable = apps.get_model("sw_demographic", "ACSVariable")
    ACSVariable.objects.all().delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_geo", "0006_c_high_priority_boundary_caches"),
    ]

    operations = [
        migrations.CreateModel(
            name="ACSVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("variable_code", models.CharField(db_index=True, max_length=20, unique=True)),
                ("label", models.TextField()),
                ("concept", models.CharField(blank=True, default="", max_length=255)),
                ("table_code", models.CharField(db_index=True, max_length=20)),
                ("universe", models.CharField(blank=True, default="", max_length=255)),
                ("predicate_type", models.CharField(blank=True, default="", max_length=20)),
                ("first_seen_vintage", models.CharField(blank=True, default="", max_length=20)),
                ("last_seen_vintage", models.CharField(blank=True, default="", max_length=20)),
            ],
            options={
                "db_table": "sw_demographic_acs_variable",
                "verbose_name": "ACS Variable",
                "ordering": ["table_code", "variable_code"],
            },
        ),
        migrations.AddIndex(
            model_name="acsvariable",
            index=models.Index(fields=["table_code", "variable_code"], name="sw_dem_acs_v_t_idx"),
        ),
        migrations.CreateModel(
            name="ACSEstimate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("boundary_type", models.CharField(db_index=True, max_length=30)),
                ("geoid", models.CharField(db_index=True, max_length=20)),
                ("value", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("moe", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("annotation", models.CharField(blank=True, default="", max_length=10)),
                (
                    "vintage",
                    models.ForeignKey(
                        limit_choices_to={"kind": "acs"},
                        on_delete=models.CASCADE,
                        related_name="acs_estimates",
                        to="sw_geo.vintage",
                    ),
                ),
                (
                    "variable",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="estimates",
                        to="sw_demographic.acsvariable",
                    ),
                ),
            ],
            options={
                "db_table": "sw_demographic_acs_estimate",
                "verbose_name": "ACS Estimate",
                "unique_together": {("vintage", "variable", "boundary_type", "geoid")},
            },
        ),
        migrations.AddIndex(
            model_name="acsestimate",
            index=models.Index(fields=["boundary_type", "geoid", "vintage"], name="sw_dem_acs_e_bgv_idx"),
        ),
        migrations.AddIndex(
            model_name="acsestimate",
            index=models.Index(fields=["variable", "vintage", "boundary_type"], name="sw_dem_acs_e_vvb_idx"),
        ),
        migrations.RunPython(_run_seed_acs_variables, _reverse_seed),
    ]
