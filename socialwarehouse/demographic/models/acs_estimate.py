"""ACS per-boundary per-vintage per-variable estimate (long format).

Per D Q2 = (a) long-format. Variables churn between releases; wide
format would break each release. Boundary keying is
(boundary_type, geoid) CharField rather than polymorphic FK (same
pragmatic shape as E and F).
"""

from django.db import models


class ACSEstimate(models.Model):
    """One row per (vintage, variable, boundary, geoid)."""

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="acs_estimates",
        limit_choices_to={"kind": "acs"},
        help_text="Polymorphic Vintage parent; should be an ACSVintage row.",
    )
    variable = models.ForeignKey(
        "sw_demographic.ACSVariable",
        on_delete=models.CASCADE,
        related_name="estimates",
    )
    boundary_type = models.CharField(
        max_length=30, db_index=True,
        help_text=(
            "Boundary type the geoid belongs to: 'state', 'county', "
            "'tract', 'block_group', 'place', 'zcta', 'puma', etc. "
            "Matches the type tokens in Address._BOUNDARY_TYPES."
        ),
    )
    geoid = models.CharField(
        max_length=20, db_index=True,
        help_text="Census GEOID for the boundary (length varies by type).",
    )
    value = models.DecimalField(
        max_digits=18, decimal_places=4,
        null=True, blank=True,
        help_text="Estimate value. NULL = Census jam value or annotation (* / ** / -).",
    )
    moe = models.DecimalField(
        max_digits=18, decimal_places=4,
        null=True, blank=True,
        help_text="Margin of error (±). NULL if not published for this variable / row.",
    )
    annotation = models.CharField(
        max_length=10, blank=True, default="",
        help_text=(
            "Census annotation for the value when not a numeric: "
            "'*', '**', '-', 'N', 'X', etc. See "
            "census.gov/data/developers/data-sets/acs-5year/data-notes.html"
        ),
    )

    class Meta:
        db_table = "sw_demographic_acs_estimate"
        verbose_name = "ACS Estimate"
        unique_together = [["vintage", "variable", "boundary_type", "geoid"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["variable", "vintage", "boundary_type"]),
        ]

    def __str__(self):
        return (
            f"{self.variable.variable_code} @ {self.boundary_type}:{self.geoid} "
            f"({self.vintage.name}) = {self.value}"
        )
