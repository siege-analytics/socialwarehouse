"""BLS QCEW per-boundary per-vintage aggregate.

Per E Q1 = (a) 2-digit NAICS (default ingest depth). Per Q2 = (b) new
vintage kind `bls-qcew` — already shipped in B PR #1 via the
`BLSQCEWVintage` subclass.

One row per (vintage, boundary_type, geoid, ownership_code,
industry_code). Long-format consistent with D's ACSEstimate.
"""

from django.db import models


# Ownership codes per BLS QCEW
# (https://www.bls.gov/cew/classifications/ownerships/qcew-ownerships.htm).
OWNERSHIP_CHOICES = [
    ("0", "Total Covered"),
    ("1", "Federal Government"),
    ("2", "State Government"),
    ("3", "Local Government"),
    ("5", "Private"),
    ("8", "Total Government"),
    ("9", "Total UI Covered"),
]


class BLSQCEWAggregate(models.Model):
    """BLS QCEW employment + wages aggregate."""

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="bls_qcew_aggregates",
        limit_choices_to={"kind": "bls-qcew"},
        help_text="Polymorphic Vintage parent; should be a BLSQCEWVintage row.",
    )
    boundary_type = models.CharField(
        max_length=30, db_index=True,
        help_text=(
            "'county' for Phase 1; 'cbsa' for Phase 2 (after C ships the "
            "cbsa boundary type)."
        ),
    )
    geoid = models.CharField(
        max_length=20, db_index=True,
        help_text="Census GEOID; 5-digit for county, 5-digit for CBSA.",
    )
    ownership_code = models.CharField(
        max_length=2, choices=OWNERSHIP_CHOICES, db_index=True,
        help_text="BLS QCEW ownership code (Total / Federal / State / etc.).",
    )
    industry_code = models.CharField(
        max_length=10, db_index=True,
        help_text=(
            "NAICS code at the depth ingested. Phase 1 default depth = 2 "
            "(sector). '10' = total of all industries (BLS convention)."
        ),
    )

    avg_monthly_employment = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Average of the three monthly employment levels in the quarter.",
    )
    total_quarterly_wages = models.BigIntegerField(
        null=True, blank=True,
        help_text="Total wages paid during the quarter, in dollars.",
    )
    avg_weekly_wage = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Average weekly wage, in dollars (BLS-computed).",
    )
    establishment_count = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of establishments (places of employment) in the quarter.",
    )

    class Meta:
        db_table = "sw_economic_bls_qcew_aggregate"
        verbose_name = "BLS QCEW Aggregate"
        unique_together = [
            ["vintage", "boundary_type", "geoid", "ownership_code", "industry_code"],
        ]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["vintage", "industry_code"]),
        ]

    def __str__(self):
        return (
            f"QCEW {self.boundary_type}:{self.geoid} "
            f"({self.vintage.name}) NAICS={self.industry_code} "
            f"own={self.ownership_code}"
        )
