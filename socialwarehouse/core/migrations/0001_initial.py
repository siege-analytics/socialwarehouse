import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="EntityIdentifier",
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
                    "entity_uuid",
                    models.UUIDField(
                        db_index=True,
                        help_text="The entity this identifier belongs to",
                    ),
                ),
                (
                    "identifier_type",
                    models.CharField(
                        help_text="Type of identifier (e.g., vendor_voter_id, fec_committee_id, ein)",
                        max_length=50,
                    ),
                ),
                (
                    "identifier_value",
                    models.CharField(
                        db_index=True,
                        help_text="The identifier value itself",
                        max_length=200,
                    ),
                ),
                (
                    "data_source",
                    models.CharField(
                        help_text="Source system this identifier came from",
                        max_length=50,
                    ),
                ),
                (
                    "jurisdiction_level",
                    models.CharField(blank=True, default="", max_length=20),
                ),
                (
                    "jurisdiction_state",
                    models.CharField(blank=True, default="", max_length=2),
                ),
                (
                    "normalizer_version",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text="Version of the normalizer used when generating the entity_uuid",
                    ),
                ),
                (
                    "valid_from",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        help_text="When this identifier became valid",
                    ),
                ),
                (
                    "valid_to",
                    models.DateTimeField(
                        blank=True,
                        help_text="When this identifier was superseded (NULL = current)",
                        null=True,
                    ),
                ),
                (
                    "ingested_at",
                    models.DateTimeField(auto_now_add=True),
                ),
            ],
            options={
                "verbose_name": "Entity Identifier",
                "verbose_name_plural": "Entity Identifiers",
                "db_table": "sw_entity_identifier",
                "unique_together": {
                    (
                        "entity_uuid",
                        "identifier_type",
                        "identifier_value",
                        "data_source",
                    )
                },
            },
        ),
        migrations.AddIndex(
            model_name="entityidentifier",
            index=models.Index(
                fields=["entity_uuid", "identifier_type"],
                name="idx_eid_uuid_type",
            ),
        ),
        migrations.AddIndex(
            model_name="entityidentifier",
            index=models.Index(
                fields=["identifier_value"],
                name="idx_eid_value",
            ),
        ),
        migrations.AddIndex(
            model_name="entityidentifier",
            index=models.Index(
                fields=["data_source", "identifier_type"],
                name="idx_eid_source_type",
            ),
        ),
    ]
