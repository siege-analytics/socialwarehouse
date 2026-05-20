"""Decennial Census per-boundary per-vintage per-variable value.

Per D design (#208) Phase 3: decennial Census tables. Same long-format
keying as ACSEstimate ((vintage, variable, boundary_type, geoid)), but
decennial is a full count (no MOE).

Phase 3a ships the PL 94-171 (redistricting data) variables — a small
curated subset that's the most-asked-for in electoral contexts. The
broader DHC (Demographic and Housing Characteristics) file is a
follow-up.
"""

from django.db import models


class DecennialVariable(models.Model):
    """Decennial Census variable catalog.

    Decennial variable codes are different from ACS (P/H prefixes
    instead of B). E.g., P1_001N = total population in 2020 PL.
    """

    variable_code = models.CharField(
        max_length=20, unique=True, db_index=True,
        help_text="Decennial variable code, e.g. 'P1_001N' (2020 PL total population).",
    )
    label = models.TextField()
    concept = models.CharField(max_length=255, blank=True, default="")
    table_code = models.CharField(
        max_length=20, db_index=True,
        help_text="Table prefix, e.g. 'P1', 'P2', 'H1'.",
    )
    universe = models.CharField(max_length=255, blank=True, default="")
    dataset = models.CharField(
        max_length=20, db_index=True,
        help_text="Decennial dataset: 'pl' (redistricting), 'dhc', etc.",
    )

    class Meta:
        db_table = "sw_demographic_decennial_variable"
        verbose_name = "Decennial Variable"
        ordering = ["table_code", "variable_code"]

    def __str__(self):
        return f"{self.variable_code}: {self.concept or self.label[:60]}"


class DecennialCount(models.Model):
    """One row per (vintage, variable, boundary_type, geoid). Full count;
    no MOE.

    Vintage FK targets the polymorphic Vintage parent with
    limit_choices_to={"kind": "census-decadal"}.
    """

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="decennial_counts",
        limit_choices_to={"kind": "census-decadal"},
        help_text="Polymorphic Vintage parent; should be a CensusDecadalVintage row.",
    )
    variable = models.ForeignKey(
        "sw_demographic.DecennialVariable",
        on_delete=models.CASCADE,
        related_name="counts",
    )
    boundary_type = models.CharField(max_length=30, db_index=True)
    geoid = models.CharField(max_length=20, db_index=True)
    value = models.BigIntegerField(
        null=True, blank=True,
        help_text="Count value. NULL means Census annotation (suppressed, etc.).",
    )
    annotation = models.CharField(
        max_length=10, blank=True, default="",
        help_text="Census annotation for non-numeric values.",
    )

    class Meta:
        db_table = "sw_demographic_decennial_count"
        verbose_name = "Decennial Count"
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
