from django.db import models

from socialwarehouse.core.agent import AgentSubtype
from socialwarehouse.core.mixins import IdentifiableModel, SourceAwareModel


class Person(SourceAwareModel, IdentifiableModel, AgentSubtype):
    """Natural person: donor, candidate, officer, employee, or other actor.

    A Person is an Agent subtype detail row. It carries name parts and
    optional birth year for matching; identity-resolution semantics
    (lifecycle, confidence) live on the linked Agent hub.

    entity_uuid is deterministic UUID5 from (data_source, source_record_id)
    so the same source person resolves to the same Person across
    re-ingests. Cross-source identity resolution (the same human across
    FEC, state ethics, and vendor files) is handled at the Agent /
    EntityIdentifier layer, not here.
    """

    full_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Full display name as it appears in the source",
    )
    given_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="First / given name (if parsed)",
    )
    family_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        db_index=True,
        help_text="Last / family name (if parsed)",
    )
    middle_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
    )
    name_suffix = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Jr, Sr, III, etc.",
    )
    birth_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Birth year, when known, for disambiguation",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "People"
        db_table = "sw_person"
        indexes = [
            models.Index(
                fields=["family_name", "given_name"],
                name="idx_person_family_given",
            ),
            models.Index(
                fields=["data_source", "source_record_id"],
                name="idx_person_source_recid",
            ),
        ]

    def __str__(self):
        return self.full_name
