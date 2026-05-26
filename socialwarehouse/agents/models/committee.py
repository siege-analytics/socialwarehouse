from django.db import models

from socialwarehouse.core.mixins import IdentifiableModel, SourceAwareModel


COMMITTEE_TYPE_CHOICES = [
    ("pac", "Political Action Committee"),
    ("super_pac", "Super PAC (Independent Expenditure)"),
    ("party", "Party Committee"),
    ("campaign", "Campaign Committee"),
    ("leadership", "Leadership PAC"),
    ("hybrid", "Hybrid PAC"),
    ("other", "Other"),
]


class Committee(SourceAwareModel, IdentifiableModel):
    """Regulatory fundraising vehicle with lifecycle tracking.

    Covers PACs, party committees, campaign committees, and similar
    entities that register with regulatory bodies to raise and spend
    money. General civic concept -- not FEC-specific. FEC-specific
    subtypes (e.g., joint fundraising committees, Carey committees)
    live in the enterprise layer.

    Natural key: (data_source, source_system_id). The source_system_id
    is the registration ID from the source regulatory body (e.g., FEC
    committee ID, state ethics commission ID). Name changes are tracked
    via the name_history JSONField.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Current legal name of the committee",
    )
    committee_type = models.CharField(
        max_length=20,
        choices=COMMITTEE_TYPE_CHOICES,
        default="other",
        db_index=True,
    )
    source_system_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Registration ID from the source regulatory body",
    )
    formation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the committee was formed or registered",
    )
    termination_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the committee was terminated (NULL = active)",
    )
    name_history = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {name, effective_from, effective_to} for name changes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Committee"
        verbose_name_plural = "Committees"
        db_table = "sw_committee"
        unique_together = [("data_source", "source_system_id")]
        indexes = [
            models.Index(
                fields=["data_source", "source_system_id"],
                name="idx_cmte_source_sysid",
            ),
            models.Index(
                fields=["committee_type", "jurisdiction_state"],
                name="idx_cmte_type_state",
            ),
        ]

    @property
    def is_active(self):
        return self.termination_date is None

    def __str__(self):
        status = "active" if self.is_active else "terminated"
        return f"{self.name} ({self.committee_type}, {status})"
