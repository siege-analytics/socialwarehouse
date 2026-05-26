import socialwarehouse.core.mixins
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_core", "0001_initial"),
    ]

    operations = [
        # Event (SourceAwareModel)
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                ("event_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("event_type", models.CharField(choices=[("transaction", "Transaction"), ("corporate", "Corporate Event"), ("spatiotemporal", "Spatio-Temporal Event"), ("electoral", "Electoral Event")], db_index=True, max_length=20)),
                ("event_date", models.DateField(db_index=True)),
                ("year", models.PositiveSmallIntegerField(db_index=True, help_text="Event year, derived from event_date")),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Event",
                "verbose_name_plural": "Events",
                "db_table": "sw_event",
            },
        ),
        # EventParticipant
        migrations.CreateModel(
            name="EventParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="sw_events.event")),
                ("agent_uuid", models.UUIDField(db_index=True)),
                ("agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("role_in_event", models.CharField(choices=[("source", "Source / From"), ("target", "Target / To"), ("subject", "Subject"), ("witness", "Witness"), ("candidate", "Candidate"), ("winner", "Winner"), ("predecessor", "Predecessor"), ("successor", "Successor"), ("affected", "Affected Party"), ("other", "Other")], db_index=True, max_length=20)),
            ],
            options={
                "verbose_name": "Event Participant",
                "verbose_name_plural": "Event Participants",
                "db_table": "sw_event_participant",
                "unique_together": {("event", "agent_uuid", "role_in_event")},
            },
        ),
        # CorporateEvent
        migrations.CreateModel(
            name="CorporateEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="corporate_detail", to="sw_events.event")),
                ("corporate_event_type", models.CharField(choices=[("merger", "Merger"), ("spinoff", "Spinoff"), ("split", "Split"), ("acquisition", "Acquisition"), ("dissolution", "Dissolution"), ("formation", "Formation")], db_index=True, max_length=20)),
                ("predecessor_uuid", models.UUIDField(blank=True, db_index=True, null=True)),
                ("successor_uuid", models.UUIDField(blank=True, db_index=True, null=True)),
                ("relationship_uuid", models.UUIDField(blank=True, help_text="Links to RelationshipCorporateSuccession from A-3", null=True)),
            ],
            options={
                "verbose_name": "Corporate Event",
                "verbose_name_plural": "Corporate Events",
                "db_table": "sw_event_corporate",
            },
        ),
        # SpatioTemporalEvent
        migrations.CreateModel(
            name="SpatioTemporalEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="spatiotemporal_detail", to="sw_events.event")),
                ("spatiotemporal_event_type", models.CharField(choices=[("redistricting_enacted", "Redistricting Plan Enacted"), ("redistricting_court_order", "Redistricting Court Order"), ("annexation", "Annexation"), ("deannexation", "De-annexation"), ("census_vintage_change", "Census Vintage Change"), ("boundary_correction", "Boundary Correction")], db_index=True, max_length=30)),
                ("redistricting_plan_id", models.CharField(blank=True, default="", max_length=100)),
                ("affected_boundary_type", models.CharField(blank=True, default="", help_text="Type of boundary affected (e.g., congressional_district, state_house)", max_length=30)),
                ("affected_jurisdiction_state", models.CharField(blank=True, db_index=True, default="", max_length=2)),
            ],
            options={
                "verbose_name": "Spatio-Temporal Event",
                "verbose_name_plural": "Spatio-Temporal Events",
                "db_table": "sw_event_spatiotemporal",
            },
        ),
        # ElectoralEvent
        migrations.CreateModel(
            name="ElectoralEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="electoral_detail", to="sw_events.event")),
                ("electoral_event_type", models.CharField(choices=[("certification", "Election Certification"), ("recount", "Recount"), ("contest_resolution", "Contest Resolution"), ("runoff_triggered", "Runoff Triggered")], db_index=True, max_length=20)),
                ("contest_uuid", models.UUIDField(blank=True, db_index=True, help_text="Links to ElectoralContest from A-4", null=True)),
                ("is_certified", models.BooleanField(default=False)),
                ("is_recount", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name": "Electoral Event",
                "verbose_name_plural": "Electoral Events",
                "db_table": "sw_event_electoral",
            },
        ),
        # Indexes
        migrations.AddIndex(model_name="event", index=models.Index(fields=["event_type", "event_date"], name="idx_event_type_date")),
        migrations.AddIndex(model_name="event", index=models.Index(fields=["event_type", "jurisdiction_state", "year"], name="idx_event_type_state_year")),
        migrations.AddIndex(model_name="eventparticipant", index=models.Index(fields=["agent_uuid"], name="idx_evpart_agent")),
        migrations.AddIndex(model_name="eventparticipant", index=models.Index(fields=["event", "role_in_event"], name="idx_evpart_event_role")),
        migrations.AddIndex(model_name="corporateevent", index=models.Index(fields=["corporate_event_type"], name="idx_evcorp_type")),
        migrations.AddIndex(model_name="corporateevent", index=models.Index(fields=["predecessor_uuid"], name="idx_evcorp_pred")),
        migrations.AddIndex(model_name="corporateevent", index=models.Index(fields=["successor_uuid"], name="idx_evcorp_succ")),
        migrations.AddIndex(model_name="spatiotemporalevent", index=models.Index(fields=["spatiotemporal_event_type"], name="idx_evst_type")),
        migrations.AddIndex(model_name="spatiotemporalevent", index=models.Index(fields=["affected_jurisdiction_state"], name="idx_evst_state")),
        migrations.AddIndex(model_name="electoralevent", index=models.Index(fields=["electoral_event_type"], name="idx_evel_type")),
        migrations.AddIndex(model_name="electoralevent", index=models.Index(fields=["contest_uuid"], name="idx_evel_contest")),
    ]
