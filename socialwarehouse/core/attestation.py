"""Central polymorphic Attestation superclass and the first FEC subclass.

An Attestation is a multi-source-provenance observation of a canonical
entity: "as of this source, parsed this way, the entity looked like
this." Many attestations accumulate per entity (the electinfo FEC data
carries hundreds per filing); the one with ``is_canonical=True`` is the
warehouse's current truth for its ``(entity_id, entity_subtype)``.

Attestation is a polymorphic supertype parallel to Agent and Event. It
generalizes beyond FEC: ``FECAttestation`` is the first concrete kind,
and entity-resolution attestations (the same person across FEC, state
ethics, and vendor files) are a planned sibling. Concrete kinds are
Django multi-table-inheritance children so each kind owns its own
columns while sharing the canonical-truth scaffolding.

Two UUIDs are in play and must not be confused:

- ``entity_uuid`` (from ``IdentifiableModel``) is *this attestation's own*
  artifact id (a UUID4, since an attestation is a resolved artifact).
- ``entity_id`` is the ``entity_uuid`` of the *attested* entity — the
  polymorphic target. Paired with ``entity_subtype`` it identifies which
  entity this attestation describes, without a Django
  GenericForeignKey (which has weaker integrity guarantees).
"""

from django.apps import apps
from django.db import models

from socialwarehouse.core.mixins import IdentifiableModel, SourceAwareModel

# Common attested entity kinds. Not enforced as choices: adopters attach
# attestations to their own entity types, so entity_subtype is an open
# vocabulary. These constants name the kinds SW resolves out of the box.
ENTITY_SUBTYPE_AGENT = "agent"
ENTITY_SUBTYPE_PERSON = "person"
ENTITY_SUBTYPE_COMMITTEE = "committee"
ENTITY_SUBTYPE_ORGANIZATION = "organization"

# Registry used by get_entity() to resolve a target entity row from its
# (entity_subtype, entity_id). Adopters extend this for their own kinds.
ENTITY_SUBTYPE_MODELS = {
    ENTITY_SUBTYPE_AGENT: ("sw_core", "Agent"),
    ENTITY_SUBTYPE_PERSON: ("sw_agents", "Person"),
    ENTITY_SUBTYPE_COMMITTEE: ("sw_agents", "Committee"),
    ENTITY_SUBTYPE_ORGANIZATION: ("sw_agents", "Organization"),
}

ATTESTATION_KIND_FEC = "fec"
ATTESTATION_KIND_ENTITY_RESOLUTION = "entity_resolution"

ATTESTATION_KIND_CHOICES = [
    (ATTESTATION_KIND_FEC, "FEC claim"),
    (ATTESTATION_KIND_ENTITY_RESOLUTION, "Entity resolution"),
]

TIER_AUTHORITATIVE = "authoritative"
TIER_PRIMARY = "primary"
TIER_SECONDARY = "secondary"
TIER_TERTIARY = "tertiary"
TIER_UNKNOWN = "unknown"

ATTESTATION_SOURCE_TIER_CHOICES = [
    (TIER_AUTHORITATIVE, "Authoritative"),
    (TIER_PRIMARY, "Primary"),
    (TIER_SECONDARY, "Secondary"),
    (TIER_TERTIARY, "Tertiary"),
    (TIER_UNKNOWN, "Unknown"),
]


class Attestation(SourceAwareModel, IdentifiableModel):
    """Polymorphic multi-source-provenance observation of an entity.

    The ``is_canonical=True`` row is the winning truth for its
    ``(entity_id, entity_subtype)`` per ``attestation_kind`` — enforced
    by a partial unique constraint.
    """

    entity_id = models.UUIDField(
        db_index=True,
        help_text="entity_uuid of the attested entity (polymorphic target)",
    )
    entity_subtype = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Kind of attested entity (agent, committee, event, filing, address, ...)",
    )
    attestation_kind = models.CharField(
        max_length=40,
        choices=ATTESTATION_KIND_CHOICES,
        db_index=True,
        help_text="Subclass discriminator (fec, entity_resolution, ...)",
    )
    attested_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="The attested data; shape varies per entity_subtype",
    )
    attested_values_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Content hash of attested_values for change detection",
    )
    attested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the attestation was produced by its source",
    )
    attested_by = models.UUIDField(
        null=True,
        blank=True,
        help_text="Parser / operator / system that produced this attestation",
    )
    attestation_source_tier = models.CharField(
        max_length=20,
        choices=ATTESTATION_SOURCE_TIER_CHOICES,
        default=TIER_UNKNOWN,
        db_index=True,
        help_text="Authority tier of the source",
    )
    sequence = models.PositiveIntegerField(
        default=0,
        help_text="Ordering within (entity_id, entity_subtype), typically by attested_at",
    )
    is_canonical = models.BooleanField(
        default=False,
        help_text="True for the canonical-source-of-truth attestation per entity per kind",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Attestation"
        verbose_name_plural = "Attestations"
        db_table = "sw_attestation"
        indexes = [
            models.Index(
                fields=["entity_id", "entity_subtype"],
                name="idx_attest_entity",
            ),
            models.Index(
                fields=["entity_subtype", "attestation_kind"],
                name="idx_attest_subtype_kind",
            ),
            models.Index(
                fields=["entity_id", "entity_subtype", "sequence"],
                name="idx_attest_entity_seq",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entity_id", "entity_subtype", "attestation_kind"],
                condition=models.Q(is_canonical=True),
                name="uq_attestation_canonical_per_entity_kind",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.entity_uuid:
            self.assign_uuid4()
        super().save(*args, **kwargs)

    def get_entity(self):
        """Resolve and return the attested entity row, or None if absent.

        Raises LookupError when ``entity_subtype`` is not in
        ``ENTITY_SUBTYPE_MODELS`` — an unregistered kind is a caller bug,
        not a missing row, so it must not resolve silently to None.
        """
        try:
            app_label, model_name = ENTITY_SUBTYPE_MODELS[self.entity_subtype]
        except KeyError as exc:
            raise LookupError(
                f"no entity model registered for entity_subtype={self.entity_subtype!r}; "
                f"register it in ENTITY_SUBTYPE_MODELS"
            ) from exc
        model = apps.get_model(app_label, model_name)
        return model.objects.filter(entity_uuid=self.entity_id).first()

    @classmethod
    def for_entity(cls, entity_subtype, entity_id, **filters):
        """Return a queryset of attestations describing one entity."""
        return cls.objects.filter(
            entity_subtype=entity_subtype, entity_id=entity_id, **filters
        )

    @classmethod
    def canonical_for(cls, entity_subtype, entity_id, attestation_kind=None):
        """Return the canonical attestation for an entity, or None.

        When ``attestation_kind`` is given, scope to that kind (there is
        one canonical per kind); otherwise return the first canonical
        across kinds.
        """
        qs = cls.for_entity(entity_subtype, entity_id, is_canonical=True)
        if attestation_kind is not None:
            qs = qs.filter(attestation_kind=attestation_kind)
        return qs.first()

    def __str__(self):
        canonical = "canonical" if self.is_canonical else "variant"
        return f"Attestation<{self.attestation_kind}> {self.entity_subtype}:{self.entity_id} ({canonical})"


class FECAttestation(Attestation):
    """FEC-form attestation: the first concrete attestation kind.

    Adds FEC-form-specific provenance. ``attestation_kind`` defaults to
    ``fec`` for every FECAttestation row.
    """

    source_artifact_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Content hash of the source artifact (e.g., the filing PDF)",
    )
    source_artifact_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Reference to the source artifact registry",
    )
    parser_version = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Version of the parser that produced this attestation",
    )
    fec_form_type = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="FEC form_type from the source filing (F3, F3X, F1, ...)",
    )
    fec_form_version = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="FEC form version",
    )

    class Meta:
        verbose_name = "FEC Attestation"
        verbose_name_plural = "FEC Attestations"
        db_table = "sw_fec_attestation"

    def save(self, *args, **kwargs):
        if not self.attestation_kind:
            self.attestation_kind = ATTESTATION_KIND_FEC
        super().save(*args, **kwargs)
