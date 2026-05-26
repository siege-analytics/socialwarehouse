from django.db import models

from socialwarehouse.core.mixins import (
    SourceAwareModel,
    generate_entity_uuid4,
)


EVENT_TYPE_CHOICES = [
    ("transaction", "Transaction"),
    ("corporate", "Corporate Event"),
    ("spatiotemporal", "Spatio-Temporal Event"),
    ("electoral", "Electoral Event"),
]

AGENT_TYPE_CHOICES = [
    ("person", "Person"),
    ("committee", "Committee"),
    ("organization", "Organization"),
]

PARTICIPANT_ROLE_CHOICES = [
    ("source", "Source / From"),
    ("target", "Target / To"),
    ("subject", "Subject"),
    ("witness", "Witness"),
    ("candidate", "Candidate"),
    ("winner", "Winner"),
    ("predecessor", "Predecessor"),
    ("successor", "Successor"),
    ("affected", "Affected Party"),
    ("other", "Other"),
]

CORPORATE_EVENT_TYPE_CHOICES = [
    ("merger", "Merger"),
    ("spinoff", "Spinoff"),
    ("split", "Split"),
    ("acquisition", "Acquisition"),
    ("dissolution", "Dissolution"),
    ("formation", "Formation"),
]

SPATIOTEMPORAL_EVENT_TYPE_CHOICES = [
    ("redistricting_enacted", "Redistricting Plan Enacted"),
    ("redistricting_court_order", "Redistricting Court Order"),
    ("annexation", "Annexation"),
    ("deannexation", "De-annexation"),
    ("census_vintage_change", "Census Vintage Change"),
    ("boundary_correction", "Boundary Correction"),
]

ELECTORAL_EVENT_TYPE_CHOICES = [
    ("certification", "Election Certification"),
    ("recount", "Recount"),
    ("contest_resolution", "Contest Resolution"),
    ("runoff_triggered", "Runoff Triggered"),
]


class Event(SourceAwareModel):
    """Unified event supertype.

    The shared query surface that ties the entire ontology together.
    "All events involving Agent X" is answered by querying EventParticipant
    joined to Event.
    """

    event_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        db_index=True,
    )
    event_date = models.DateField(db_index=True)
    year = models.PositiveSmallIntegerField(
        db_index=True,
        help_text="Event year, derived from event_date",
    )
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Event"
        verbose_name_plural = "Events"
        db_table = "sw_event"
        indexes = [
            models.Index(
                fields=["event_type", "event_date"],
                name="idx_event_type_date",
            ),
            models.Index(
                fields=["event_type", "jurisdiction_state", "year"],
                name="idx_event_type_state_year",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.event_date:
            self.year = self.event_date.year
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.event_type}: {self.event_date}"


class EventParticipant(models.Model):
    """Bridge table: links agents to events with a role.

    Enables the shared query surface: "all events involving Agent X"
    across all event subtypes.
    """

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    agent_uuid = models.UUIDField(db_index=True)
    agent_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
    )
    role_in_event = models.CharField(
        max_length=20,
        choices=PARTICIPANT_ROLE_CHOICES,
        db_index=True,
    )

    class Meta:
        verbose_name = "Event Participant"
        verbose_name_plural = "Event Participants"
        db_table = "sw_event_participant"
        unique_together = [("event", "agent_uuid", "role_in_event")]
        indexes = [
            models.Index(
                fields=["agent_uuid"],
                name="idx_evpart_agent",
            ),
            models.Index(
                fields=["event", "role_in_event"],
                name="idx_evpart_event_role",
            ),
        ]

    def __str__(self):
        return f"{self.agent_uuid} ({self.role_in_event}) in {self.event}"


class CorporateEvent(models.Model):
    """Corporate event: merger, spinoff, split, acquisition, dissolution."""

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="corporate_detail",
    )
    corporate_event_type = models.CharField(
        max_length=20,
        choices=CORPORATE_EVENT_TYPE_CHOICES,
        db_index=True,
    )
    predecessor_uuid = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )
    successor_uuid = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )
    relationship_uuid = models.UUIDField(
        null=True,
        blank=True,
        help_text="Links to RelationshipCorporateSuccession from A-3",
    )

    class Meta:
        verbose_name = "Corporate Event"
        verbose_name_plural = "Corporate Events"
        db_table = "sw_event_corporate"
        indexes = [
            models.Index(
                fields=["corporate_event_type"],
                name="idx_evcorp_type",
            ),
            models.Index(
                fields=["predecessor_uuid"],
                name="idx_evcorp_pred",
            ),
            models.Index(
                fields=["successor_uuid"],
                name="idx_evcorp_succ",
            ),
        ]

    def __str__(self):
        return f"{self.corporate_event_type}: {self.event.event_date}"


class SpatioTemporalEvent(models.Model):
    """Redistricting, annexation, Census vintage change.

    Triggers boundary re-assignment for affected addresses.
    """

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="spatiotemporal_detail",
    )
    spatiotemporal_event_type = models.CharField(
        max_length=30,
        choices=SPATIOTEMPORAL_EVENT_TYPE_CHOICES,
        db_index=True,
    )
    redistricting_plan_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    affected_boundary_type = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Type of boundary affected (e.g., congressional_district, state_house)",
    )
    affected_jurisdiction_state = models.CharField(
        max_length=2,
        blank=True,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Spatio-Temporal Event"
        verbose_name_plural = "Spatio-Temporal Events"
        db_table = "sw_event_spatiotemporal"
        indexes = [
            models.Index(
                fields=["spatiotemporal_event_type"],
                name="idx_evst_type",
            ),
            models.Index(
                fields=["affected_jurisdiction_state"],
                name="idx_evst_state",
            ),
        ]

    def __str__(self):
        return f"{self.spatiotemporal_event_type}: {self.event.event_date}"


class ElectoralEvent(models.Model):
    """Election certification, recount, contest resolution."""

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="electoral_detail",
    )
    electoral_event_type = models.CharField(
        max_length=20,
        choices=ELECTORAL_EVENT_TYPE_CHOICES,
        db_index=True,
    )
    contest_uuid = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Links to ElectoralContest from A-4",
    )
    is_certified = models.BooleanField(default=False)
    is_recount = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Electoral Event"
        verbose_name_plural = "Electoral Events"
        db_table = "sw_event_electoral"
        indexes = [
            models.Index(
                fields=["electoral_event_type"],
                name="idx_evel_type",
            ),
            models.Index(
                fields=["contest_uuid"],
                name="idx_evel_contest",
            ),
        ]

    def __str__(self):
        cert = " (certified)" if self.is_certified else ""
        return f"{self.electoral_event_type}{cert}: {self.event.event_date}"
