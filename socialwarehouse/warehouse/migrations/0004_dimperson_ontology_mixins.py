"""
Add SourceAwareModel and IdentifiableModel fields to DimPerson (#286 / A-1).

Step 1: Add all columns as nullable.
Step 2: Backfill existing rows with derived values.

entity_uuid stays nullable until backfill is verified complete;
a follow-on migration will tighten to NOT NULL.
"""

import uuid

from django.db import migrations, models

from socialwarehouse.core.mixins import generate_entity_uuid5


def backfill_dimperson_mixin_fields(apps, schema_editor):
    """Backfill existing DimPerson rows with ontology mixin values.

    - data_source: vendor short code -> canonical source name
    - jurisdiction_level: 'state' (voter files are state-level products)
    - jurisdiction_state: from registration_state
    - source_record_id: from vendor_voter_id
    - entity_uuid: UUID5 from (vendor, vendor_voter_id)
    """
    DimPerson = apps.get_model("sw_warehouse", "DimPerson")
    VENDOR_SOURCE_MAP = {
        "ts": "targetsmart",
        "l2": "l2",
        "pdi": "pdi",
        "catalist": "catalist",
    }
    batch_size = 5000
    qs = DimPerson.objects.filter(entity_uuid__isnull=True)
    total = qs.count()
    if total == 0:
        return

    updated = 0
    while True:
        batch = list(
            DimPerson.objects.filter(entity_uuid__isnull=True)
            .only("id", "vendor", "vendor_voter_id", "registration_state")[:batch_size]
        )
        if not batch:
            break
        for row in batch:
            row.data_source = VENDOR_SOURCE_MAP.get(row.vendor, row.vendor or "")
            row.jurisdiction_level = "state"
            row.jurisdiction_state = row.registration_state or ""
            row.source_record_id = row.vendor_voter_id or ""
            row.entity_uuid = generate_entity_uuid5(
                row.vendor or "", row.vendor_voter_id or ""
            )
        DimPerson.objects.bulk_update(
            batch,
            ["data_source", "jurisdiction_level", "jurisdiction_state",
             "source_record_id", "entity_uuid"],
            batch_size=batch_size,
        )
        updated += len(batch)


def reverse_backfill(apps, schema_editor):
    """Reverse backfill: null out the mixin fields."""
    DimPerson = apps.get_model("sw_warehouse", "DimPerson")
    DimPerson.objects.all().update(
        data_source="",
        jurisdiction_level="",
        jurisdiction_state="",
        source_record_id="",
        ingested_at=None,
        entity_uuid=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("sw_warehouse", "0003_person_score_vote_history"),
        ("sw_core", "0001_initial"),
    ]

    operations = [
        # Step 1: Add SourceAwareModel fields (nullable/blank defaults)
        migrations.AddField(
            model_name="dimperson",
            name="data_source",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Source system identifier (e.g., targetsmart, tx_ethics, census_acs)",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="dimperson",
            name="jurisdiction_level",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Jurisdiction level: federal, state, county, municipal",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="dimperson",
            name="jurisdiction_state",
            field=models.CharField(
                blank=True,
                default="",
                help_text="State abbreviation (if applicable)",
                max_length=2,
            ),
        ),
        migrations.AddField(
            model_name="dimperson",
            name="source_record_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Original record ID from the source system",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="dimperson",
            name="ingested_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the record was ingested into SW",
                null=True,
            ),
        ),
        # Step 1: Add IdentifiableModel field (nullable for transition)
        migrations.AddField(
            model_name="dimperson",
            name="entity_uuid",
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text="Stable UUID5 from (vendor, vendor_voter_id). Nullable during backfill transition.",
                null=True,
                unique=True,
            ),
        ),
        # Step 1: Add composite index for cross-source lookups
        migrations.AddIndex(
            model_name="dimperson",
            index=models.Index(
                fields=["data_source", "source_record_id"],
                name="idx_dp_source_record",
            ),
        ),
        # Step 2: Backfill existing rows
        migrations.RunPython(
            backfill_dimperson_mixin_fields,
            reverse_code=reverse_backfill,
        ),
    ]
