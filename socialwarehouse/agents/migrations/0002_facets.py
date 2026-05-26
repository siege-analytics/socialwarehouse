import socialwarehouse.core.mixins
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_agents", "0001_initial"),
    ]

    operations = [
        # Classification
        migrations.CreateModel(
            name="Classification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, help_text="Start of this facet's validity period", null=True)),
                ("effective_to", models.DateField(blank=True, help_text="End of this facet's validity (NULL = current)", null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("classification_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("agent_uuid", models.UUIDField(db_index=True, help_text="entity_uuid of the classified agent")),
                ("agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], db_index=True, max_length=20)),
                ("classification_type", models.CharField(choices=[("tax_status", "Tax Status (e.g., 501(c)(3), 501(c)(4))"), ("partisan_alignment", "Partisan Alignment"), ("committee_subtype", "Committee Subtype"), ("candidate_status", "Candidate Status (incumbent, challenger, open)"), ("voter_category", "Voter Category"), ("other", "Other")], db_index=True, max_length=30)),
                ("value", models.CharField(help_text="Classification value (e.g., '501(c)(3)', 'incumbent', 'super_voter')", max_length=100)),
            ],
            options={"verbose_name": "Classification", "verbose_name_plural": "Classifications", "db_table": "sw_classification"},
        ),
        # Role
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, help_text="Start of this facet's validity period", null=True)),
                ("effective_to", models.DateField(blank=True, help_text="End of this facet's validity (NULL = current)", null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("role_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("agent_uuid", models.UUIDField(db_index=True, help_text="entity_uuid of the agent holding this role")),
                ("agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], db_index=True, max_length=20)),
                ("role_type", models.CharField(choices=[("treasurer", "Treasurer"), ("candidate", "Candidate for Office"), ("custodian", "Custodian of Records"), ("officer", "Officer"), ("director", "Director / Board Member"), ("registered_agent", "Registered Agent"), ("lobbyist", "Lobbyist"), ("other", "Other")], db_index=True, max_length=30)),
                ("counterparty_uuid", models.UUIDField(blank=True, db_index=True, help_text="entity_uuid of the counterparty", null=True)),
                ("counterparty_type", models.CharField(blank=True, choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], default="", max_length=20)),
            ],
            options={"verbose_name": "Role", "verbose_name_plural": "Roles", "db_table": "sw_role"},
        ),
        # RelationshipSimple
        migrations.CreateModel(
            name="RelationshipSimple",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("relationship_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("from_agent_uuid", models.UUIDField(db_index=True)),
                ("from_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("to_agent_uuid", models.UUIDField(db_index=True)),
                ("to_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("relationship_type", models.CharField(choices=[("spouse_of", "Spouse Of"), ("affiliated_with", "Affiliated With"), ("employer_of", "Employer Of"), ("employed_by", "Employed By")], db_index=True, max_length=30)),
            ],
            options={"verbose_name": "Simple Relationship", "verbose_name_plural": "Simple Relationships", "db_table": "sw_relationship_simple"},
        ),
        # RelationshipSponsor
        migrations.CreateModel(
            name="RelationshipSponsor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("relationship_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("sponsor_uuid", models.UUIDField(db_index=True, help_text="Organization entity_uuid")),
                ("sponsored_uuid", models.UUIDField(db_index=True, help_text="Committee entity_uuid")),
            ],
            options={"verbose_name": "Sponsor Relationship", "verbose_name_plural": "Sponsor Relationships", "db_table": "sw_relationship_sponsor"},
        ),
        # RelationshipControl
        migrations.CreateModel(
            name="RelationshipControl",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("relationship_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("controller_uuid", models.UUIDField(db_index=True)),
                ("controller_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("controlled_uuid", models.UUIDField(db_index=True)),
                ("controlled_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("control_type", models.CharField(choices=[("controls", "Controls"), ("controlled_by", "Controlled By")], default="controls", max_length=30)),
            ],
            options={"verbose_name": "Control Relationship", "verbose_name_plural": "Control Relationships", "db_table": "sw_relationship_control"},
        ),
        # RelationshipSubsidiary
        migrations.CreateModel(
            name="RelationshipSubsidiary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("relationship_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("parent_uuid", models.UUIDField(db_index=True)),
                ("child_uuid", models.UUIDField(db_index=True)),
            ],
            options={"verbose_name": "Subsidiary Relationship", "verbose_name_plural": "Subsidiary Relationships", "db_table": "sw_relationship_subsidiary"},
        ),
        # RelationshipCorporateSuccession
        migrations.CreateModel(
            name="RelationshipCorporateSuccession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("relationship_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("predecessor_uuid", models.UUIDField(db_index=True)),
                ("successor_uuid", models.UUIDField(db_index=True)),
                ("succession_type", models.CharField(choices=[("merger", "Merger"), ("spinoff", "Spinoff"), ("split", "Split"), ("rename", "Rename / Continuation")], db_index=True, max_length=20)),
                ("succession_date", models.DateField(blank=True, null=True)),
            ],
            options={"verbose_name": "Corporate Succession", "verbose_name_plural": "Corporate Successions", "db_table": "sw_relationship_succession"},
        ),
        # RelationshipDAFConduit
        migrations.CreateModel(
            name="RelationshipDAFConduit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("relationship_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("daf_uuid", models.UUIDField(db_index=True, help_text="DAF entity_uuid")),
                ("recipient_uuid", models.UUIDField(db_index=True, help_text="Recipient entity_uuid")),
                ("donor_uuid", models.UUIDField(blank=True, db_index=True, help_text="Original donor entity_uuid (if known)", null=True)),
            ],
            options={"verbose_name": "DAF Conduit Relationship", "verbose_name_plural": "DAF Conduit Relationships", "db_table": "sw_relationship_daf_conduit"},
        ),
        # Indexes for Classification
        migrations.AddIndex(model_name="classification", index=models.Index(fields=["agent_uuid", "classification_type"], name="idx_cls_agent_type")),
        migrations.AddIndex(model_name="classification", index=models.Index(fields=["effective_from", "effective_to"], name="idx_cls_temporal")),
        migrations.AddIndex(model_name="classification", index=models.Index(fields=["jurisdiction_level", "jurisdiction_state"], name="idx_cls_jurisdiction")),
        # Indexes for Role
        migrations.AddIndex(model_name="role", index=models.Index(fields=["agent_uuid", "role_type"], name="idx_role_agent_type")),
        migrations.AddIndex(model_name="role", index=models.Index(fields=["counterparty_uuid"], name="idx_role_counterparty")),
        migrations.AddIndex(model_name="role", index=models.Index(fields=["effective_from", "effective_to"], name="idx_role_temporal")),
        # Indexes for RelationshipSimple
        migrations.AddIndex(model_name="relationshipsimple", index=models.Index(fields=["from_agent_uuid"], name="idx_relsim_from")),
        migrations.AddIndex(model_name="relationshipsimple", index=models.Index(fields=["to_agent_uuid"], name="idx_relsim_to")),
        migrations.AddIndex(model_name="relationshipsimple", index=models.Index(fields=["effective_from", "effective_to"], name="idx_relsim_temporal")),
        # Indexes for RelationshipSponsor
        migrations.AddIndex(model_name="relationshipsponsor", index=models.Index(fields=["sponsor_uuid"], name="idx_relspon_sponsor")),
        migrations.AddIndex(model_name="relationshipsponsor", index=models.Index(fields=["sponsored_uuid"], name="idx_relspon_sponsored")),
        # Indexes for RelationshipControl
        migrations.AddIndex(model_name="relationshipcontrol", index=models.Index(fields=["controller_uuid"], name="idx_relctrl_controller")),
        migrations.AddIndex(model_name="relationshipcontrol", index=models.Index(fields=["controlled_uuid"], name="idx_relctrl_controlled")),
        # Indexes for RelationshipSubsidiary
        migrations.AddIndex(model_name="relationshipsubsidiary", index=models.Index(fields=["parent_uuid"], name="idx_relsub_parent")),
        migrations.AddIndex(model_name="relationshipsubsidiary", index=models.Index(fields=["child_uuid"], name="idx_relsub_child")),
        # Indexes for RelationshipCorporateSuccession
        migrations.AddIndex(model_name="relationshipcorporatesuccession", index=models.Index(fields=["predecessor_uuid"], name="idx_relsucc_predecessor")),
        migrations.AddIndex(model_name="relationshipcorporatesuccession", index=models.Index(fields=["successor_uuid"], name="idx_relsucc_successor")),
        # Indexes for RelationshipDAFConduit
        migrations.AddIndex(model_name="relationshipdafconduit", index=models.Index(fields=["daf_uuid"], name="idx_reldaf_daf")),
        migrations.AddIndex(model_name="relationshipdafconduit", index=models.Index(fields=["recipient_uuid"], name="idx_reldaf_recipient")),
    ]
