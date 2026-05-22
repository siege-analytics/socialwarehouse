# Hand-authored migration for SW#251 (Person + score + vote history).
# Generated locally without makemigrations because the local dev env
# does not have a GDAL version Django can detect; CI / docker env will.
# Mirrors what `manage.py makemigrations warehouse` would produce.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_warehouse", "0002_remove_dimredistrictingcycle_decennial_census_year_and_more"),
        ("sw_geo", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DimPerson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vendor", models.CharField(choices=[("pdi", "PDI"), ("l2", "L2"), ("catalist", "Catalist"), ("ts", "TargetSmart")], db_index=True, max_length=16)),
                ("vendor_voter_id", models.CharField(db_index=True, max_length=128)),
                ("first_name", models.CharField(blank=True, default="", max_length=128)),
                ("middle_name", models.CharField(blank=True, default="", max_length=128)),
                ("last_name", models.CharField(blank=True, default="", max_length=128)),
                ("name_suffix", models.CharField(blank=True, default="", max_length=32)),
                ("dob", models.DateField(blank=True, null=True)),
                ("gender", models.CharField(blank=True, default="", max_length=32)),
                ("ethnicity", models.CharField(blank=True, default="", max_length=64)),
                ("language", models.CharField(blank=True, default="", max_length=64)),
                ("registration_status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive"), ("purged", "Purged"), ("pending", "Pending"), ("not_registered", "Not registered"), ("deceased", "Deceased")], db_index=True, default="not_registered", max_length=32)),
                ("registration_state", models.CharField(db_index=True, max_length=2)),
                ("registration_date", models.DateField(blank=True, null=True)),
                ("party_registration", models.CharField(blank=True, default="", max_length=64)),
                ("voter_status_reason", models.CharField(blank=True, default="", max_length=128)),
                ("vendor_address_line1", models.CharField(blank=True, default="", max_length=255)),
                ("vendor_address_line2", models.CharField(blank=True, default="", max_length=255)),
                ("vendor_city", models.CharField(blank=True, default="", max_length=128)),
                ("vendor_state", models.CharField(blank=True, default="", max_length=2)),
                ("vendor_zip", models.CharField(blank=True, default="", max_length=5)),
                ("vendor_zip4", models.CharField(blank=True, default="", max_length=4)),
                ("vendor_address_supplied_at", models.DateField(blank=True, null=True)),
                ("household_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("household_size", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("is_head_of_household", models.BooleanField(default=False)),
                ("general_election_count", models.PositiveIntegerField(default=0)),
                ("primary_election_count", models.PositiveIntegerField(default=0)),
                ("total_vote_count", models.PositiveIntegerField(default=0)),
                ("last_voted_at", models.DateField(blank=True, null=True)),
                ("vote_frequency_category", models.CharField(blank=True, default="", max_length=32)),
                ("pdi_extras", models.JSONField(blank=True, default=dict)),
                ("l2_extras", models.JSONField(blank=True, default=dict)),
                ("catalist_extras", models.JSONField(blank=True, default=dict)),
                ("ts_extras", models.JSONField(blank=True, default=dict)),
                ("last_loaded_from_vendor", models.CharField(blank=True, choices=[("pdi", "PDI"), ("l2", "L2"), ("catalist", "Catalist"), ("ts", "TargetSmart")], default="", max_length=16)),
                ("last_loaded_at", models.DateTimeField(blank=True, null=True)),
                ("silver_source_path", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("address", models.ForeignKey(blank=True, help_text="Canonical address (resolved via geo pipeline). Importers that cannot resolve an address may set null; consumer policy decides.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="people", to="sw_geo.address")),
            ],
            options={
                "verbose_name": "Person Dimension",
                "verbose_name_plural": "Person Dimensions",
                "unique_together": {("vendor", "vendor_voter_id")},
                "indexes": [
                    models.Index(fields=["registration_state", "registration_status"], name="sw_warehous_registr_d63afa_idx"),
                    models.Index(fields=["last_name", "first_name"], name="sw_warehous_last_na_69cb1f_idx"),
                    models.Index(fields=["dob"], name="sw_warehous_dob_d3ec57_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="FactPersonScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score_type", models.CharField(db_index=True, max_length=128)),
                ("value", models.FloatField()),
                ("source_vendor", models.CharField(choices=[("pdi", "PDI"), ("l2", "L2"), ("catalist", "Catalist"), ("ts", "TargetSmart")], max_length=16)),
                ("methodology_version", models.CharField(blank=True, default="", max_length=64)),
                ("scored_at", models.DateTimeField()),
                ("loaded_at", models.DateTimeField(auto_now_add=True)),
                ("person", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scores", to="sw_warehouse.dimperson")),
            ],
            options={
                "db_table": "sw_fact_person_score",
                "verbose_name": "Person Score Fact",
                "verbose_name_plural": "Person Score Facts",
                "unique_together": {("person", "score_type", "source_vendor", "methodology_version")},
                "indexes": [
                    models.Index(fields=["score_type", "source_vendor"], name="sw_fact_per_score_t_3b9a02_idx"),
                    models.Index(fields=["person", "score_type"], name="sw_fact_per_person__9c4d4f_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="FactVoteHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("election_date", models.DateField(db_index=True)),
                ("election_type", models.CharField(choices=[("general", "General"), ("primary", "Primary"), ("runoff", "Runoff"), ("special", "Special"), ("local", "Local"), ("other", "Other")], max_length=16)),
                ("voted_method", models.CharField(choices=[("in_person", "In person"), ("absentee", "Absentee"), ("mail", "Mail"), ("early", "Early"), ("provisional", "Provisional"), ("unknown", "Unknown")], default="unknown", max_length=16)),
                ("source_vendor", models.CharField(choices=[("pdi", "PDI"), ("l2", "L2"), ("catalist", "Catalist"), ("ts", "TargetSmart")], max_length=16)),
                ("loaded_at", models.DateTimeField(auto_now_add=True)),
                ("person", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vote_history", to="sw_warehouse.dimperson")),
            ],
            options={
                "db_table": "sw_fact_vote_history",
                "verbose_name": "Vote History Fact",
                "verbose_name_plural": "Vote History Facts",
                "unique_together": {("person", "election_date", "election_type", "source_vendor")},
                "indexes": [
                    models.Index(fields=["person", "election_date"], name="sw_fact_vot_person__a8c1d3_idx"),
                    models.Index(fields=["election_date", "election_type"], name="sw_fact_vot_electio_4e2f78_idx"),
                ],
            },
        ),
    ]
