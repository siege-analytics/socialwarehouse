import uuid

from django.db import models


SW_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "socialwarehouse.siegeanalytics.com")

NORMALIZER_VERSION = 1


def normalize_v1(*components):
    """Normalize components for UUID5 generation (version 1).

    Lowercase, strip whitespace, join with pipe separator.
    """
    parts = []
    for c in components:
        if c is None:
            parts.append("")
        else:
            parts.append(str(c).strip().lower())
    return "|".join(parts)


NORMALIZERS = {
    1: normalize_v1,
}


def generate_entity_uuid5(*components, normalizer_version=NORMALIZER_VERSION):
    """Generate a deterministic UUID5 from normalized components.

    Same inputs always produce the same UUID. Used for entities with
    pre-existing identity (Person, Committee, Organization, Office, Seat).
    """
    normalizer = NORMALIZERS[normalizer_version]
    normalized = normalizer(*components)
    return uuid.uuid5(SW_NAMESPACE, normalized)


def generate_entity_uuid4():
    """Generate a random UUID4 for resolved artifacts.

    Used for entities without pre-existing identity (Transactions,
    Events, Attestations) where deterministic generation isn't possible.
    """
    return uuid.uuid4()


class SourceAwareModel(models.Model):
    """Track where data came from: which source, which jurisdiction."""

    data_source = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text="Source system identifier (e.g., targetsmart, tx_ethics, census_acs)",
    )
    jurisdiction_level = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Jurisdiction level: federal, state, county, municipal",
    )
    jurisdiction_state = models.CharField(
        max_length=2,
        blank=True,
        default="",
        help_text="State abbreviation (if applicable)",
    )
    source_record_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Original record ID from the source system",
    )
    ingested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the record was ingested into SW",
    )

    class Meta:
        abstract = True


class IdentifiableModel(models.Model):
    """Stable UUID identification for cross-source entity resolution."""

    entity_uuid = models.UUIDField(
        unique=True,
        editable=False,
        help_text="Stable UUID. UUID5 for identity entities, UUID4 for artifacts. Immutable once assigned.",
    )

    class Meta:
        abstract = True

    def assign_uuid5(self, *components, normalizer_version=NORMALIZER_VERSION):
        """Assign a deterministic UUID5 from identity components.

        Only call this when creating a new entity. Once assigned,
        entity_uuid must never change (immutability rule).
        """
        self.entity_uuid = generate_entity_uuid5(
            *components, normalizer_version=normalizer_version
        )
        return self.entity_uuid

    def assign_uuid4(self):
        """Assign a random UUID4 for resolved artifacts."""
        self.entity_uuid = generate_entity_uuid4()
        return self.entity_uuid
