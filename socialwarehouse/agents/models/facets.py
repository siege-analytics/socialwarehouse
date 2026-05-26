from django.db import models

from socialwarehouse.core.mixins import generate_entity_uuid4


AGENT_TYPE_CHOICES = [
    ("person", "Person"),
    ("committee", "Committee"),
    ("organization", "Organization"),
]

CLASSIFICATION_TYPE_CHOICES = [
    ("tax_status", "Tax Status (e.g., 501(c)(3), 501(c)(4))"),
    ("partisan_alignment", "Partisan Alignment"),
    ("committee_subtype", "Committee Subtype"),
    ("candidate_status", "Candidate Status (incumbent, challenger, open)"),
    ("voter_category", "Voter Category"),
    ("other", "Other"),
]

ROLE_TYPE_CHOICES = [
    ("treasurer", "Treasurer"),
    ("candidate", "Candidate for Office"),
    ("custodian", "Custodian of Records"),
    ("officer", "Officer"),
    ("director", "Director / Board Member"),
    ("registered_agent", "Registered Agent"),
    ("lobbyist", "Lobbyist"),
    ("other", "Other"),
]

RELATIONSHIP_SIMPLE_TYPE_CHOICES = [
    ("spouse_of", "Spouse Of"),
    ("affiliated_with", "Affiliated With"),
    ("employer_of", "Employer Of"),
    ("employed_by", "Employed By"),
]

RELATIONSHIP_CONTROL_TYPE_CHOICES = [
    ("controls", "Controls"),
    ("controlled_by", "Controlled By"),
]

RELATIONSHIP_SUCCESSION_TYPE_CHOICES = [
    ("merger", "Merger"),
    ("spinoff", "Spinoff"),
    ("split", "Split"),
    ("rename", "Rename / Continuation"),
]


class _EffectiveDatedFacet(models.Model):
    """Base for all effective-dated facet models."""

    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text="Start of this facet's validity period",
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text="End of this facet's validity (NULL = current)",
    )
    data_source = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    @property
    def is_current(self):
        return self.effective_to is None


class Classification(_EffectiveDatedFacet):
    """What an agent IS: tax status, partisan alignment, candidate status, etc.

    Multiple concurrent classifications allowed per agent. Each has its
    own effective date range. An agent can be both "501(c)(4)" and
    "nonpartisan" simultaneously.
    """

    classification_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    agent_uuid = models.UUIDField(
        db_index=True,
        help_text="entity_uuid of the classified agent",
    )
    agent_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
        db_index=True,
    )
    classification_type = models.CharField(
        max_length=30,
        choices=CLASSIFICATION_TYPE_CHOICES,
        db_index=True,
    )
    value = models.CharField(
        max_length=100,
        help_text="Classification value (e.g., '501(c)(3)', 'incumbent', 'super_voter')",
    )

    class Meta:
        verbose_name = "Classification"
        verbose_name_plural = "Classifications"
        db_table = "sw_classification"
        indexes = [
            models.Index(
                fields=["agent_uuid", "classification_type"],
                name="idx_cls_agent_type",
            ),
            models.Index(
                fields=["effective_from", "effective_to"],
                name="idx_cls_temporal",
            ),
            models.Index(
                fields=["jurisdiction_level", "jurisdiction_state"],
                name="idx_cls_jurisdiction",
            ),
        ]

    def __str__(self):
        return f"{self.classification_type}={self.value} -> {self.agent_uuid}"


class Role(_EffectiveDatedFacet):
    """What an agent DOES relative to a counterparty: treasurer, candidate, etc.

    Temporal: a person can be treasurer of Committee A from 2020-2022,
    then treasurer of Committee B from 2023-present. Multiple concurrent
    roles allowed.
    """

    role_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    agent_uuid = models.UUIDField(
        db_index=True,
        help_text="entity_uuid of the agent holding this role",
    )
    agent_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
        db_index=True,
    )
    role_type = models.CharField(
        max_length=30,
        choices=ROLE_TYPE_CHOICES,
        db_index=True,
    )
    counterparty_uuid = models.UUIDField(
        db_index=True,
        null=True,
        blank=True,
        help_text="entity_uuid of the counterparty (e.g., the committee the person is treasurer of)",
    )
    counterparty_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        db_table = "sw_role"
        indexes = [
            models.Index(
                fields=["agent_uuid", "role_type"],
                name="idx_role_agent_type",
            ),
            models.Index(
                fields=["counterparty_uuid"],
                name="idx_role_counterparty",
            ),
            models.Index(
                fields=["effective_from", "effective_to"],
                name="idx_role_temporal",
            ),
        ]

    def __str__(self):
        cp = f" -> {self.counterparty_uuid}" if self.counterparty_uuid else ""
        return f"{self.role_type}: {self.agent_uuid}{cp}"


class RelationshipSimple(_EffectiveDatedFacet):
    """Simple bidirectional relationship: spouse_of, affiliated_with, employer_of."""

    relationship_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    from_agent_uuid = models.UUIDField(db_index=True)
    from_agent_type = models.CharField(max_length=20, choices=AGENT_TYPE_CHOICES)
    to_agent_uuid = models.UUIDField(db_index=True)
    to_agent_type = models.CharField(max_length=20, choices=AGENT_TYPE_CHOICES)
    relationship_type = models.CharField(
        max_length=30,
        choices=RELATIONSHIP_SIMPLE_TYPE_CHOICES,
        db_index=True,
    )

    class Meta:
        verbose_name = "Simple Relationship"
        verbose_name_plural = "Simple Relationships"
        db_table = "sw_relationship_simple"
        indexes = [
            models.Index(fields=["from_agent_uuid"], name="idx_relsim_from"),
            models.Index(fields=["to_agent_uuid"], name="idx_relsim_to"),
            models.Index(fields=["effective_from", "effective_to"], name="idx_relsim_temporal"),
        ]

    def __str__(self):
        return f"{self.from_agent_uuid} {self.relationship_type} {self.to_agent_uuid}"


class RelationshipSponsor(_EffectiveDatedFacet):
    """Sponsor relationship: connected organization that sponsors a committee."""

    relationship_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    sponsor_uuid = models.UUIDField(db_index=True, help_text="Organization entity_uuid")
    sponsored_uuid = models.UUIDField(db_index=True, help_text="Committee entity_uuid")

    class Meta:
        verbose_name = "Sponsor Relationship"
        verbose_name_plural = "Sponsor Relationships"
        db_table = "sw_relationship_sponsor"
        indexes = [
            models.Index(fields=["sponsor_uuid"], name="idx_relspon_sponsor"),
            models.Index(fields=["sponsored_uuid"], name="idx_relspon_sponsored"),
        ]

    def __str__(self):
        return f"{self.sponsor_uuid} sponsors {self.sponsored_uuid}"


class RelationshipControl(_EffectiveDatedFacet):
    """Control relationship: one entity controls another."""

    relationship_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    controller_uuid = models.UUIDField(db_index=True)
    controller_type = models.CharField(max_length=20, choices=AGENT_TYPE_CHOICES)
    controlled_uuid = models.UUIDField(db_index=True)
    controlled_type = models.CharField(max_length=20, choices=AGENT_TYPE_CHOICES)
    control_type = models.CharField(
        max_length=30,
        choices=RELATIONSHIP_CONTROL_TYPE_CHOICES,
        default="controls",
    )

    class Meta:
        verbose_name = "Control Relationship"
        verbose_name_plural = "Control Relationships"
        db_table = "sw_relationship_control"
        indexes = [
            models.Index(fields=["controller_uuid"], name="idx_relctrl_controller"),
            models.Index(fields=["controlled_uuid"], name="idx_relctrl_controlled"),
        ]

    def __str__(self):
        return f"{self.controller_uuid} {self.control_type} {self.controlled_uuid}"


class RelationshipSubsidiary(_EffectiveDatedFacet):
    """Parent/child corporate relationship."""

    relationship_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    parent_uuid = models.UUIDField(db_index=True)
    child_uuid = models.UUIDField(db_index=True)

    class Meta:
        verbose_name = "Subsidiary Relationship"
        verbose_name_plural = "Subsidiary Relationships"
        db_table = "sw_relationship_subsidiary"
        indexes = [
            models.Index(fields=["parent_uuid"], name="idx_relsub_parent"),
            models.Index(fields=["child_uuid"], name="idx_relsub_child"),
        ]

    def __str__(self):
        return f"{self.parent_uuid} parent of {self.child_uuid}"


class RelationshipCorporateSuccession(_EffectiveDatedFacet):
    """Corporate succession: merger, spinoff, split, rename."""

    relationship_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    predecessor_uuid = models.UUIDField(db_index=True)
    successor_uuid = models.UUIDField(db_index=True)
    succession_type = models.CharField(
        max_length=20,
        choices=RELATIONSHIP_SUCCESSION_TYPE_CHOICES,
        db_index=True,
    )
    succession_date = models.DateField(
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Corporate Succession"
        verbose_name_plural = "Corporate Successions"
        db_table = "sw_relationship_succession"
        indexes = [
            models.Index(fields=["predecessor_uuid"], name="idx_relsucc_predecessor"),
            models.Index(fields=["successor_uuid"], name="idx_relsucc_successor"),
        ]

    def __str__(self):
        return f"{self.predecessor_uuid} {self.succession_type} -> {self.successor_uuid}"


class RelationshipDAFConduit(_EffectiveDatedFacet):
    """Donor-Advised Fund conduit pass-through relationship."""

    relationship_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    daf_uuid = models.UUIDField(db_index=True, help_text="DAF entity_uuid")
    recipient_uuid = models.UUIDField(db_index=True, help_text="Recipient entity_uuid")
    donor_uuid = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Original donor entity_uuid (if known)",
    )

    class Meta:
        verbose_name = "DAF Conduit Relationship"
        verbose_name_plural = "DAF Conduit Relationships"
        db_table = "sw_relationship_daf_conduit"
        indexes = [
            models.Index(fields=["daf_uuid"], name="idx_reldaf_daf"),
            models.Index(fields=["recipient_uuid"], name="idx_reldaf_recipient"),
        ]

    def __str__(self):
        return f"{self.daf_uuid} -> {self.recipient_uuid}"
