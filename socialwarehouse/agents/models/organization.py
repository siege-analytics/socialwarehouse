from django.db import models

from socialwarehouse.core.agent import AgentSubtype
from socialwarehouse.core.mixins import IdentifiableModel, SourceAwareModel


INDUSTRY_SYSTEM_CHOICES = [
    ("naics", "NAICS (North American Industry Classification System)"),
    ("sic", "SIC (Standard Industrial Classification)"),
    ("other", "Other"),
]


class Organization(SourceAwareModel, IdentifiableModel, AgentSubtype):
    """Employer, vendor, consultant, union, corporation, or other entity.

    General civic concept covering non-committee organizational entities.
    Matched by name + jurisdiction + industry across sources. Unlike
    Committee, Organization does not have regulatory registration IDs
    as a universal natural key -- matching is softer.

    entity_uuid is deterministic UUID5 from (name, jurisdiction_state,
    industry_code) for cross-source resolution.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Legal or commonly-known name of the organization",
    )
    industry_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="NAICS or SIC code for the organization's primary industry",
    )
    industry_system = models.CharField(
        max_length=10,
        choices=INDUSTRY_SYSTEM_CHOICES,
        default="naics",
        help_text="Classification system for industry_code",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        db_table = "sw_organization"
        indexes = [
            models.Index(
                fields=["name", "jurisdiction_state"],
                name="idx_org_name_state",
            ),
            models.Index(
                fields=["industry_code", "industry_system"],
                name="idx_org_industry",
            ),
        ]

    def __str__(self):
        industry = f" [{self.industry_code}]" if self.industry_code else ""
        return f"{self.name}{industry}"
