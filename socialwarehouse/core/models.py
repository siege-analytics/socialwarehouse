import uuid

from django.db import models
from django.utils import timezone


class EntityIdentifier(models.Model):
    """Append-only log of entity identifiers for cross-source resolution.

    One entity_uuid can have multiple identifiers (from different sources).
    One identifier_value can map to multiple entity_uuids (ambiguity).
    The combination (entity_uuid, identifier_type, identifier_value,
    data_source) is unique — the same identifier from the same source
    for the same entity is recorded once.
    """

    entity_uuid = models.UUIDField(
        db_index=True,
        help_text="The entity this identifier belongs to",
    )
    identifier_type = models.CharField(
        max_length=50,
        help_text="Type of identifier (e.g., vendor_voter_id, fec_committee_id, ein)",
    )
    identifier_value = models.CharField(
        max_length=200,
        db_index=True,
        help_text="The identifier value itself",
    )
    data_source = models.CharField(
        max_length=50,
        help_text="Source system this identifier came from",
    )
    jurisdiction_level = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )
    jurisdiction_state = models.CharField(
        max_length=2,
        blank=True,
        default="",
    )
    normalizer_version = models.PositiveSmallIntegerField(
        default=1,
        help_text="Version of the normalizer used when generating the entity_uuid",
    )
    valid_from = models.DateTimeField(
        default=timezone.now,
        help_text="When this identifier became valid",
    )
    valid_to = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this identifier was superseded (NULL = current)",
    )
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_entity_identifier"
        verbose_name = "Entity Identifier"
        verbose_name_plural = "Entity Identifiers"
        unique_together = [
            ("entity_uuid", "identifier_type", "identifier_value", "data_source"),
        ]
        indexes = [
            models.Index(
                fields=["entity_uuid", "identifier_type"],
                name="idx_eid_uuid_type",
            ),
            models.Index(
                fields=["identifier_value"],
                name="idx_eid_value",
            ),
            models.Index(
                fields=["data_source", "identifier_type"],
                name="idx_eid_source_type",
            ),
        ]

    def __str__(self):
        return f"{self.identifier_type}={self.identifier_value} ({self.data_source}) -> {self.entity_uuid}"

    @classmethod
    def register(cls, entity_uuid, identifier_type, identifier_value, data_source,
                 jurisdiction_level="", jurisdiction_state="", normalizer_version=1):
        """Register an identifier for an entity (idempotent)."""
        obj, created = cls.objects.get_or_create(
            entity_uuid=entity_uuid,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            data_source=data_source,
            defaults={
                "jurisdiction_level": jurisdiction_level,
                "jurisdiction_state": jurisdiction_state,
                "normalizer_version": normalizer_version,
            },
        )
        return obj, created

    @classmethod
    def resolve(cls, identifier_type, identifier_value, data_source=None):
        """Look up entity_uuid(s) by identifier.

        Returns a queryset of EntityIdentifier rows. If data_source is
        provided, filters to that source. Caller decides how to handle
        ambiguity (multiple UUIDs for the same identifier).
        """
        qs = cls.objects.filter(
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            valid_to__isnull=True,
        )
        if data_source:
            qs = qs.filter(data_source=data_source)
        return qs
