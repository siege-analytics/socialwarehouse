from django.core.exceptions import ValidationError
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
    ("narrative", "Narrative Event"),
]

EVENT_STATE_CHOICES = [
    ("active", "Active"),
    ("amended", "Amended"),
    ("withdrawn", "Withdrawn"),
    ("superseded", "Superseded"),
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

EXPOSURE_CLASS_PUBLIC_ACTOR = "public_actor"
EXPOSURE_CLASS_INCIDENTAL_PRIVATE = "incidental_private"

EXPOSURE_CLASS_CHOICES = [
    (EXPOSURE_CLASS_PUBLIC_ACTOR, "Public Actor"),
    (EXPOSURE_CLASS_INCIDENTAL_PRIVATE, "Incidental Private"),
]

NARRATIVE_EVENT_TYPE_CHOICES = [
    ("speech", "Speech"),
    ("scandal", "Scandal"),
    ("endorsement", "Endorsement"),
    ("pac_formation", "PAC Formation"),
    ("pledge_letter", "Pledge Letter"),
    ("indictment", "Indictment"),
    ("resignation", "Resignation"),
    ("other", "Other"),
]

DURATION_MODE_BOUNDED = "bounded"
DURATION_MODE_STRUCTURAL = "structural"

DURATION_MODE_CHOICES = [
    (DURATION_MODE_BOUNDED, "Bounded (fixed pre/post window)"),
    (DURATION_MODE_STRUCTURAL, "Structural / Open-Ended"),
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

    # Canonicalization layer (SW#349). All event subtypes inherit these by
    # being attached to an Event. canonical_attestation is a fast-lookup
    # cache pointing at the winning Attestation; the source of truth is
    # Attestation.is_canonical (partial-unique-enforced on the Attestation
    # side). attestation_disagreement flags conflicting source attestations.
    canonical_attestation = models.ForeignKey(
        "sw_core.Attestation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="canonical_for_events",
        help_text="Fast-lookup cache of the canonical attestation; truth is Attestation.is_canonical",
    )
    attestation_disagreement = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when source attestations for this event conflict",
    )
    is_amended = models.BooleanField(
        default=False,
        help_text="True when this event has been amended by a later revision",
    )
    amendment_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of amendments applied to this event",
    )
    event_state = models.CharField(
        max_length=20,
        choices=EVENT_STATE_CHOICES,
        default="active",
        db_index=True,
        help_text="active / amended / withdrawn / superseded",
    )

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
            models.Index(
                fields=["event_type", "event_state"],
                name="idx_event_type_state",
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
    exposure_class = models.CharField(
        max_length=20,
        choices=EXPOSURE_CLASS_CHOICES,
        default=EXPOSURE_CLASS_PUBLIC_ACTOR,
        db_index=True,
        help_text=(
            "public_actor (default) chose their political exposure; "
            "incidental_private did not and requires sourcing_note "
            "justifying inclusion"
        ),
    )
    sourcing_note = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Required when exposure_class=incidental_private: why this "
            "private individual is named in this event"
        ),
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
        constraints = [
            # incidental_private participants didn't choose public exposure,
            # so a sourcing justification is required at write time -- not
            # just a nullable column. Enforced at the DB (fires on every
            # write path, including raw .objects.create()/.update(), unlike
            # clean(), which Django only calls from ModelForm/full_clean()).
            # sourcing_note__regex=r"\S" requires at least one non-whitespace
            # character, so this rejects whitespace-only notes the same way
            # clean() below does -- the two layers are kept in lockstep on
            # purpose; a prior draft that only checked sourcing_note="" at
            # the DB layer let ``sourcing_note="   "`` slip through every
            # write path except clean(), silently defeating the guardrail.
            models.CheckConstraint(
                condition=~models.Q(exposure_class=EXPOSURE_CLASS_INCIDENTAL_PRIVATE)
                | models.Q(sourcing_note__regex=r"\S"),
                name="ck_evpart_sourcing_note_required",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.exposure_class == EXPOSURE_CLASS_INCIDENTAL_PRIVATE
            and not self.sourcing_note.strip()
        ):
            raise ValidationError(
                {
                    "sourcing_note": (
                        "sourcing_note is required when exposure_class is "
                        "incidental_private."
                    )
                }
            )

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


class NarrativeEvent(models.Model):
    """Analyst-curated real-world event: speech, scandal, endorsement, ...

    Sourced/attested per the shared ``agent_attestations`` pattern via the
    parent ``Event``'s ``canonical_attestation`` -- provenance is load-bearing
    here the same as everywhere else in the ontology.

    Duration is analyst-selected at entry, not auto-detected:
    ``bounded`` (a fixed pre/post window around ``event.event_date``,
    independently settable) or ``structural`` (open-ended; closed later
    by setting ``effective_to`` -- the same nullable-close pattern used by
    ``Vintage``/``Seat``, where NULL means still in effect). Event-to-event
    supersession linkage (one event closing another's regime) is tracked
    separately in siege-analytics/socialwarehouse#370 and is out of scope
    here.
    """

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="narrative_detail",
    )
    narrative_event_type = models.CharField(
        max_length=30,
        choices=NARRATIVE_EVENT_TYPE_CHOICES,
        db_index=True,
    )
    duration_mode = models.CharField(
        max_length=20,
        choices=DURATION_MODE_CHOICES,
        default=DURATION_MODE_BOUNDED,
        db_index=True,
    )
    window_pre_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Bounded mode only: days before event.event_date the window opens",
    )
    window_post_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Bounded mode only: days after event.event_date the window closes",
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Structural mode only. NULL = still in effect / open-ended; "
            "non-null = the date the regime this event opened was closed."
        ),
    )

    class Meta:
        verbose_name = "Narrative Event"
        verbose_name_plural = "Narrative Events"
        db_table = "sw_event_narrative"
        indexes = [
            models.Index(
                fields=["narrative_event_type"],
                name="idx_evnarr_type",
            ),
            models.Index(
                fields=["duration_mode"],
                name="idx_evnarr_duration_mode",
            ),
        ]
        constraints = [
            # The two duration modes carry mutually exclusive fields:
            # bounded rows use window_pre_days/window_post_days (at least
            # one must be set -- "bounded" with no bound is meaningless)
            # and must not set effective_to; structural rows use
            # effective_to and must not set the window fields.
            models.CheckConstraint(
                condition=(
                    models.Q(duration_mode=DURATION_MODE_BOUNDED, effective_to__isnull=True)
                    & ~models.Q(window_pre_days__isnull=True, window_post_days__isnull=True)
                )
                | models.Q(
                    duration_mode=DURATION_MODE_STRUCTURAL,
                    window_pre_days__isnull=True,
                    window_post_days__isnull=True,
                ),
                name="ck_evnarr_duration_mode_fields",
            ),
        ]

    def clean(self):
        super().clean()
        if self.duration_mode == DURATION_MODE_BOUNDED:
            errors = {}
            if self.effective_to is not None:
                errors["effective_to"] = "effective_to only applies in structural mode."
            if self.window_pre_days is None and self.window_post_days is None:
                msg = (
                    "at least one of window_pre_days/window_post_days is "
                    "required in bounded mode."
                )
                errors["window_pre_days"] = msg
                errors["window_post_days"] = msg
            if errors:
                raise ValidationError(errors)
        elif self.duration_mode == DURATION_MODE_STRUCTURAL:
            errors = {}
            if self.window_pre_days is not None:
                errors["window_pre_days"] = "window_pre_days only applies in bounded mode."
            if self.window_post_days is not None:
                errors["window_post_days"] = "window_post_days only applies in bounded mode."
            if errors:
                raise ValidationError(errors)

    def __str__(self):
        return f"{self.narrative_event_type}: {self.event.event_date}"
