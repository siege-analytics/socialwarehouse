import socialwarehouse.core.mixins
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_core", "0001_initial"),
    ]

    operations = [
        # Office (SourceAwareModel + IdentifiableModel)
        migrations.CreateModel(
            name="Office",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                # SourceAwareModel fields
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                # IdentifiableModel field
                ("entity_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                # Office-specific fields
                ("name", models.CharField(max_length=255)),
                ("chamber", models.CharField(blank=True, choices=[("senate", "Senate"), ("house", "House"), ("upper", "Upper Chamber (state)"), ("lower", "Lower Chamber (state)"), ("at_large", "At-Large"), ("executive", "Executive")], db_index=True, default="", max_length=20)),
                ("district_number", models.CharField(blank=True, db_index=True, default="", max_length=10)),
            ],
            options={
                "verbose_name": "Office",
                "verbose_name_plural": "Offices",
                "db_table": "sw_office",
                "unique_together": {("jurisdiction_level", "jurisdiction_state", "chamber", "district_number")},
            },
        ),
        # Seat
        migrations.CreateModel(
            name="Seat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seat_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("office", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seats", to="sw_political.office")),
                ("redistricting_plan_id", models.CharField(blank=True, db_index=True, default="", help_text="Identifier for the redistricting plan (e.g., '2020_enacted')", max_length=100)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("boundary_geoid", models.CharField(blank=True, db_index=True, default="", help_text="GEOID of the geographic boundary for this seat", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Seat",
                "verbose_name_plural": "Seats",
                "db_table": "sw_seat",
                "unique_together": {("office", "redistricting_plan_id")},
            },
        ),
        # Election (SourceAwareModel)
        migrations.CreateModel(
            name="Election",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                # SourceAwareModel fields
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                # Election-specific fields
                ("election_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("election_date", models.DateField(db_index=True)),
                ("election_type", models.CharField(choices=[("general", "General"), ("primary", "Primary"), ("special", "Special"), ("runoff", "Runoff")], db_index=True, max_length=20)),
                ("year", models.PositiveSmallIntegerField(db_index=True, help_text="Election year, derived from election_date")),
            ],
            options={
                "verbose_name": "Election",
                "verbose_name_plural": "Elections",
                "db_table": "sw_election",
                "unique_together": {("election_date", "jurisdiction_state", "election_type")},
            },
        ),
        # ElectoralContest
        migrations.CreateModel(
            name="ElectoralContest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("contest_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("election", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contests", to="sw_political.election")),
                ("office", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contests", to="sw_political.office")),
                ("seat", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contests", to="sw_political.seat")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Electoral Contest",
                "verbose_name_plural": "Electoral Contests",
                "db_table": "sw_electoral_contest",
                "unique_together": {("election", "office")},
            },
        ),
        # OfficeTerm
        migrations.CreateModel(
            name="OfficeTerm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("term_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("office", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="terms", to="sw_political.office")),
                ("person_uuid", models.UUIDField(db_index=True, help_text="entity_uuid of the Person holding this office")),
                ("start_date", models.DateField(db_index=True)),
                ("end_date", models.DateField(blank=True, db_index=True, null=True)),
                ("term_type", models.CharField(choices=[("elected", "Elected"), ("appointed", "Appointed"), ("special_election", "Special Election"), ("acting", "Acting / Interim")], db_index=True, default="elected", max_length=20)),
                ("congress_number", models.PositiveSmallIntegerField(blank=True, help_text="Congress number (e.g., 118 for 118th Congress). Federal only.", null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Office Term",
                "verbose_name_plural": "Office Terms",
                "db_table": "sw_office_term",
            },
        ),
        # Indexes
        migrations.AddIndex(model_name="office", index=models.Index(fields=["jurisdiction_level", "jurisdiction_state"], name="idx_office_jurisdiction")),
        migrations.AddIndex(model_name="office", index=models.Index(fields=["chamber", "district_number"], name="idx_office_chamber_district")),
        migrations.AddIndex(model_name="seat", index=models.Index(fields=["effective_from", "effective_to"], name="idx_seat_temporal")),
        migrations.AddIndex(model_name="seat", index=models.Index(fields=["boundary_geoid"], name="idx_seat_geoid")),
        migrations.AddIndex(model_name="election", index=models.Index(fields=["year", "jurisdiction_state"], name="idx_election_year_state")),
        migrations.AddIndex(model_name="election", index=models.Index(fields=["election_date", "election_type"], name="idx_election_date_type")),
        migrations.AddIndex(model_name="electoralcontest", index=models.Index(fields=["election", "office"], name="idx_contest_election_office")),
        migrations.AddIndex(model_name="officeterm", index=models.Index(fields=["office", "person_uuid"], name="idx_term_office_person")),
        migrations.AddIndex(model_name="officeterm", index=models.Index(fields=["start_date", "end_date"], name="idx_term_temporal")),
        migrations.AddIndex(model_name="officeterm", index=models.Index(fields=["congress_number"], name="idx_term_congress")),
    ]
