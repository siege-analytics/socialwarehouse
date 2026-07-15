"""Polymorphic Agent supertype and the subtype-link base.

The ``Agent`` is the shared identity hub for actors that act in civic and
financial data: people, committees, and organizations. It carries the
identity-resolution semantics (lifecycle state, resolution confidence)
that are common across every actor kind, while the concrete subtype
detail (a Committee's registration ID, a Person's name parts) stays in
the domain apps.

Concrete subtypes link to an Agent through ``AgentSubtype``, an abstract
base that adds a nullable one-to-one ``agent`` field. The link is
nullable so existing rows in ``sw_committee`` / ``sw_organization`` remain
valid after the migration and can be backfilled incrementally.
"""

from django.db import models

from socialwarehouse.core.mixins import (
    IdentifiableModel,
    SourceAwareModel,
    generate_entity_uuid5,
)


AGENT_SUBTYPE_PERSON = "person"
AGENT_SUBTYPE_COMMITTEE = "committee"
AGENT_SUBTYPE_ORGANIZATION = "organization"

AGENT_SUBTYPE_CHOICES = [
    (AGENT_SUBTYPE_PERSON, "Person"),
    (AGENT_SUBTYPE_COMMITTEE, "Committee"),
    (AGENT_SUBTYPE_ORGANIZATION, "Organization"),
]

LIFECYCLE_ACTIVE = "active"
LIFECYCLE_DISSOLVED = "dissolved"
LIFECYCLE_MERGED = "merged"
LIFECYCLE_UNKNOWN = "unknown"

LIFECYCLE_STATE_CHOICES = [
    (LIFECYCLE_ACTIVE, "Active"),
    (LIFECYCLE_DISSOLVED, "Dissolved"),
    (LIFECYCLE_MERGED, "Merged into another agent"),
    (LIFECYCLE_UNKNOWN, "Unknown"),
]


class Agent(SourceAwareModel, IdentifiableModel):
    """Polymorphic actor hub: person, committee, or organization.

    One Agent row is the canonical identity for an actor regardless of
    which concrete subtype carries its detail. The ``subtype`` field names
    the concrete kind; the matching one-to-one reverse accessor
    (``agent.person`` / ``agent.committee`` / ``agent.organization``)
    resolves to the detail row.

    ``entity_uuid`` is a deterministic UUID5 over
    ``(subtype, data_source, source_record_id)`` so the same actor
    resolves to the same Agent across re-ingests of the same source row.
    """

    subtype = models.CharField(
        max_length=20,
        choices=AGENT_SUBTYPE_CHOICES,
        db_index=True,
        help_text="Concrete agent kind; names the one-to-one detail accessor",
    )
    lifecycle_state = models.CharField(
        max_length=20,
        choices=LIFECYCLE_STATE_CHOICES,
        default=LIFECYCLE_ACTIVE,
        db_index=True,
        help_text="active / dissolved / merged / unknown",
    )
    resolution_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Identity-resolution confidence in [0, 1]; NULL if not scored",
    )
    dissolved_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date the agent dissolved (NULL unless lifecycle_state is dissolved)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Agent"
        verbose_name_plural = "Agents"
        db_table = "sw_agent"
        indexes = [
            models.Index(
                fields=["subtype", "lifecycle_state"],
                name="idx_agent_subtype_state",
            ),
            models.Index(
                fields=["data_source", "source_record_id"],
                name="idx_agent_source_recid",
            ),
        ]
        constraints = [
            # resolution_confidence is a probability in [0, 1] (NULL when
            # unscored). Enforced at the DB so an out-of-range score from an
            # identity-resolution producer fails loudly instead of being
            # stored silently. DecimalField(max_digits=5) alone would accept
            # values up to 9.9999 and negatives.
            models.CheckConstraint(
                condition=models.Q(resolution_confidence__isnull=True)
                | models.Q(
                    resolution_confidence__gte=0,
                    resolution_confidence__lte=1,
                ),
                name="ck_agent_resolution_confidence_0_1",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.entity_uuid:
            self.assign_uuid5(self.subtype, self.data_source, self.source_record_id)
        super().save(*args, **kwargs)

    @staticmethod
    def make_entity_uuid(subtype, data_source, source_record_id):
        """Return the deterministic UUID5 an Agent row would carry.

        Lets a caller compute the hub UUID before the row exists (for
        example, to wire a subtype detail row to its Agent in one pass).
        """
        return generate_entity_uuid5(subtype, data_source, source_record_id)

    def get_subtype_instance(self):
        """Resolve to the concrete subtype detail row, or None.

        Dispatches on ``subtype`` to the matching one-to-one reverse
        accessor. Returns None when the detail row has not been linked
        yet (the link is nullable by design).
        """
        related = getattr(self, self.subtype, None)
        return related

    @property
    def is_active(self):
        return self.lifecycle_state == LIFECYCLE_ACTIVE

    def __str__(self):
        return f"Agent<{self.subtype}> {self.entity_uuid} ({self.lifecycle_state})"


class AgentSubtype(models.Model):
    """Abstract base linking a concrete subtype detail row to its Agent.

    Adds a nullable one-to-one ``agent`` field. The reverse accessor on
    Agent is the lowercased subclass name (``agent.person`` etc.), which
    is what :meth:`Agent.get_subtype_instance` dispatches on.

    The link is nullable so the migration that introduces it does not
    require backfilling every existing detail row in the same change.
    """

    agent = models.OneToOneField(
        "sw_core.Agent",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s",
        related_query_name="%(class)s",
        help_text="The Agent identity hub this detail row belongs to",
    )

    class Meta:
        abstract = True

    def link_agent(self, agent):
        """Attach this detail row to an Agent hub and persist the link."""
        self.agent = agent
        self.save(update_fields=["agent"])
        return agent
