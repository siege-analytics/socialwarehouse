import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_agents", "0002_facets"),
        ("sw_core", "0002_agent"),
    ]

    operations = [
        migrations.AddField(
            model_name="committee",
            name="agent",
            field=models.OneToOneField(
                blank=True,
                help_text="The Agent identity hub this detail row belongs to",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s",
                related_query_name="%(class)s",
                to="sw_core.agent",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="agent",
            field=models.OneToOneField(
                blank=True,
                help_text="The Agent identity hub this detail row belongs to",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s",
                related_query_name="%(class)s",
                to="sw_core.agent",
            ),
        ),
        migrations.CreateModel(
            name="Person",
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
                    "full_name",
                    models.CharField(
                        db_index=True,
                        help_text="Full display name as it appears in the source",
                        max_length=255,
                    ),
                ),
                (
                    "given_name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="First / given name (if parsed)",
                        max_length=120,
                    ),
                ),
                (
                    "family_name",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Last / family name (if parsed)",
                        max_length=120,
                    ),
                ),
                (
                    "middle_name",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                (
                    "name_suffix",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Jr, Sr, III, etc.",
                        max_length=20,
                    ),
                ),
                (
                    "birth_year",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="Birth year, when known, for disambiguation",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "agent",
                    models.OneToOneField(
                        blank=True,
                        help_text="The Agent identity hub this detail row belongs to",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s",
                        related_query_name="%(class)s",
                        to="sw_core.agent",
                    ),
                ),
            ],
            options={
                "verbose_name": "Person",
                "verbose_name_plural": "People",
                "db_table": "sw_person",
                "indexes": [
                    models.Index(
                        fields=["family_name", "given_name"],
                        name="idx_person_family_given",
                    ),
                    models.Index(
                        fields=["data_source", "source_record_id"],
                        name="idx_person_source_recid",
                    ),
                ],
            },
        ),
    ]
