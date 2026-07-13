"""Abstract base classes for the three attestation variant-linking shapes.

Not every entity family links to the central :class:`Attestation` the
same way. The electinfo data shows three distinct shapes:

- **thin subtype-link** (``committee_attestations``, ``person_attestations``):
  a polymorphic Attestation points at a subtype detail through a thin
  index row that records the subtype and source.
- **junction** (``filing_attestations``): a plain many-to-many between an
  entity and its attestations.
- **full resolution** (``address_attestations``): the row records the RAW
  input, the RESOLVED canonical target, and resolution metadata — not a
  simple "link entity to attestation" shape.

Each ships here as a Django **abstract base class**. Adopters subclass
per entity type in their own app (e.g.
``class CommitteeAttestationLink(AttestationSubtypeLink)``); SW ships no
concrete subclass, so there are no tables and no migration on the
template side.
"""

from django.db import models


class AttestationSubtypeLink(models.Model):
    """Thin link from an Attestation to a typed subtype detail row.

    Preserves the Attestation FK while letting the linked subtype be
    specific. Adopters subclass per entity type and add whatever subtype
    FK they need alongside this base's fields.

    Shape: ``(attestation, entity_subtype, source_type)``.
    """

    attestation = models.ForeignKey(
        "sw_core.Attestation",
        on_delete=models.CASCADE,
        related_name="%(class)s_links",
        related_query_name="%(class)s_link",
        help_text="The attestation this link indexes",
    )
    entity_subtype = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Kind of subtype detail this link points at",
    )
    source_type = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        help_text="Source-system type that produced the link",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class AttestationJunction(models.Model):
    """Many-to-many junction between an entity and its attestations.

    A single entity can carry many attestations; an attestation can
    describe many entities. This base supplies the Attestation side;
    adopters add the entity FK on their concrete subclass and declare a
    ``unique_together`` over the pair.

    Shape: ``(entity_fk [adopter-supplied], attestation)``.
    """

    attestation = models.ForeignKey(
        "sw_core.Attestation",
        on_delete=models.CASCADE,
        related_name="%(class)s_junctions",
        related_query_name="%(class)s_junction",
        help_text="The attestation linked to the adopter's entity",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


RESOLUTION_PENDING = "pending"
RESOLUTION_RESOLVED = "resolved"
RESOLUTION_AMBIGUOUS = "ambiguous"
RESOLUTION_UNRESOLVED = "unresolved"

RESOLUTION_STATUS_CHOICES = [
    (RESOLUTION_PENDING, "Pending"),
    (RESOLUTION_RESOLVED, "Resolved"),
    (RESOLUTION_AMBIGUOUS, "Ambiguous"),
    (RESOLUTION_UNRESOLVED, "Unresolved"),
]


class ResolutionAttestation(models.Model):
    """Full-resolution shape: raw input, resolved target, and metadata.

    Unlike the link/junction shapes, a resolution attestation records the
    RAW input that was resolved, the RESOLVED canonical target, and how
    the resolution was reached. Address resolution is the canonical case
    (``address_attestations``). Adopters subclass per resolved entity
    type and typically add a concrete FK to the resolved target
    alongside the ``resolved_entity_id`` / ``resolved_entity_subtype``
    pair kept here for uniform polymorphic access.

    Shape: ``raw_input`` + ``resolved_*`` + ``resolution_*`` metadata.
    """

    raw_input = models.JSONField(
        default=dict,
        blank=True,
        help_text="The raw, unresolved input that was submitted for resolution",
    )
    resolved_entity_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="entity_uuid of the resolved canonical target (NULL until resolved)",
    )
    resolved_entity_subtype = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Kind of the resolved canonical target",
    )
    resolution_status = models.CharField(
        max_length=20,
        choices=RESOLUTION_STATUS_CHOICES,
        default=RESOLUTION_PENDING,
        db_index=True,
        help_text="Outcome of the resolution attempt",
    )
    resolution_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Resolution confidence in [0, 1]; NULL if not scored",
    )
    resolver_source = models.CharField(
        max_length=60,
        blank=True,
        default="",
        help_text="Resolver / pipeline that produced this resolution",
    )
    run_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Resolution run that produced this row, for lineage",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_resolved(self):
        return self.resolution_status == RESOLUTION_RESOLVED and self.resolved_entity_id is not None
