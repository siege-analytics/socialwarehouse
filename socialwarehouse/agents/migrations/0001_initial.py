from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Committee",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "data_source",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Source system identifier (e.g., targetsmart, tx_ethics, census_acs)",
                        max_length=50,
                    ),
                ),
                (
                    "jurisdiction_level",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Jurisdiction level: federal, state, county, municipal",
                        max_length=20,
                    ),
                ),
                (
                    "jurisdiction_state",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="State abbreviation (if applicable)",
                        max_length=2,
                    ),
                ),
                (
                    "source_record_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Original record ID from the source system",
                        max_length=100,
                    ),
                ),
                (
                    "ingested_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the record was ingested into SW",
                        null=True,
                    ),
                ),
                (
                    "entity_uuid",
                    models.UUIDField(
                        editable=False,
                        help_text="Stable UUID. UUID5 for identity entities, UUID4 for artifacts. Immutable once assigned.",
                        unique=True,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        db_index=True,
                        help_text="Current legal name of the committee",
                        max_length=255,
                    ),
                ),
                (
                    "committee_type",
                    models.CharField(
                        choices=[
                            ("pac", "Political Action Committee"),
                            ("super_pac", "Super PAC (Independent Expenditure)"),
                            ("party", "Party Committee"),
                            ("campaign", "Campaign Committee"),
                            ("leadership", "Leadership PAC"),
                            ("hybrid", "Hybrid PAC"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        default="other",
                        max_length=20,
                    ),
                ),
                (
                    "source_system_id",
                    models.CharField(
                        db_index=True,
                        help_text="Registration ID from the source regulatory body",
                        max_length=100,
                    ),
                ),
                (
                    "formation_date",
                    models.DateField(
                        blank=True,
                        help_text="Date the committee was formed or registered",
                        null=True,
                    ),
                ),
                (
                    "termination_date",
                    models.DateField(
                        blank=True,
                        help_text="Date the committee was terminated (NULL = active)",
                        null=True,
                    ),
                ),
                (
                    "name_history",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of {name, effective_from, effective_to} for name changes",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Committee",
                "verbose_name_plural": "Committees",
                "db_table": "sw_committee",
                "unique_together": {("data_source", "source_system_id")},
            },
        ),
        migrations.CreateModel(
            name="Organization",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "data_source",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Source system identifier (e.g., targetsmart, tx_ethics, census_acs)",
                        max_length=50,
                    ),
                ),
                (
                    "jurisdiction_level",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Jurisdiction level: federal, state, county, municipal",
                        max_length=20,
                    ),
                ),
                (
                    "jurisdiction_state",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="State abbreviation (if applicable)",
                        max_length=2,
                    ),
                ),
                (
                    "source_record_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Original record ID from the source system",
                        max_length=100,
                    ),
                ),
                (
                    "ingested_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the record was ingested into SW",
                        null=True,
                    ),
                ),
                (
                    "entity_uuid",
                    models.UUIDField(
                        editable=False,
                        help_text="Stable UUID. UUID5 for identity entities, UUID4 for artifacts. Immutable once assigned.",
                        unique=True,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        db_index=True,
                        help_text="Legal or commonly-known name of the organization",
                        max_length=255,
                    ),
                ),
                (
                    "industry_code",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="NAICS or SIC code for the organization's primary industry",
                        max_length=20,
                    ),
                ),
                (
                    "industry_system",
                    models.CharField(
                        choices=[
                            ("naics", "NAICS (North American Industry Classification System)"),
                            ("sic", "SIC (Standard Industrial Classification)"),
                            ("other", "Other"),
                        ],
                        default="naics",
                        help_text="Classification system for industry_code",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Organization",
                "verbose_name_plural": "Organizations",
                "db_table": "sw_organization",
            },
        ),
        migrations.AddIndex(
            model_name="committee",
            index=models.Index(
                fields=["data_source", "source_system_id"],
                name="idx_cmte_source_sysid",
            ),
        ),
        migrations.AddIndex(
            model_name="committee",
            index=models.Index(
                fields=["committee_type", "jurisdiction_state"],
                name="idx_cmte_type_state",
            ),
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(
                fields=["name", "jurisdiction_state"],
                name="idx_org_name_state",
            ),
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(
                fields=["industry_code", "industry_system"],
                name="idx_org_industry",
            ),
        ),
    ]
