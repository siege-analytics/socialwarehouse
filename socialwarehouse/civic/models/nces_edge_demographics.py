"""NCES EDGE per-school-district demographic estimates.

Per F design (#210) Q1 = (b) CCD + EDGE both. Phase 1a + 1b shipped
CCD (district + school aggregates). This is the EDGE half: Census-
derived per-district demographic snapshots that NCES re-publishes
on a different release cadence than the warehouse's ACS estimates.

EDGE distributes a per-district summary of ACS estimates for the
school-age population, computed against district boundaries (which
ACS itself doesn't directly publish). One row per (vintage, geoid).
"""

from django.db import models


class NCESDistrictEDGEDemographics(models.Model):
    """One row per LEA per EDGE release; demographics inside district boundaries."""

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="nces_edge_demographics",
        limit_choices_to={"kind": "nces-school-year"},
        help_text="Polymorphic Vintage parent; should be an NCESSchoolYearVintage row.",
    )
    boundary_type = models.CharField(
        max_length=30, default="school_district", db_index=True,
    )
    geoid = models.CharField(
        max_length=7, db_index=True,
        help_text="LEAID; joins to NCESDistrictAggregate.geoid.",
    )
    state_fips = models.CharField(max_length=2, blank=True, default="", db_index=True)

    # Census-derived source the EDGE release used (e.g. "ACS 2018-2022").
    source_acs_endpoint = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Source ACS 5-year endpoint vintage (e.g. '2018-2022').",
    )

    # ── Population estimates (within school-district boundary) ───────────
    total_population = models.PositiveIntegerField(null=True, blank=True)
    population_5_17 = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="School-age population (ages 5-17) within district boundary.",
    )
    population_under_5 = models.PositiveIntegerField(null=True, blank=True)

    # ── School-age population by race/ethnicity ──────────────────────────
    pop_5_17_white_nh = models.PositiveIntegerField(null=True, blank=True)
    pop_5_17_black_nh = models.PositiveIntegerField(null=True, blank=True)
    pop_5_17_asian_nh = models.PositiveIntegerField(null=True, blank=True)
    pop_5_17_aian_nh = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="American Indian / Alaska Native, non-Hispanic.",
    )
    pop_5_17_nhpi_nh = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Native Hawaiian / Pacific Islander, non-Hispanic.",
    )
    pop_5_17_two_or_more_nh = models.PositiveIntegerField(null=True, blank=True)
    pop_5_17_hispanic = models.PositiveIntegerField(null=True, blank=True)

    # ── School-age poverty ───────────────────────────────────────────────
    pop_5_17_in_poverty = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="School-age (5-17) population with income below poverty.",
    )
    pop_5_17_poverty_rate = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        help_text="School-age poverty rate (0.0-1.0).",
    )

    # ── Households + housing ─────────────────────────────────────────────
    households_total = models.PositiveIntegerField(null=True, blank=True)
    households_with_school_age = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Households with at least one child age 5-17.",
    )
    median_household_income = models.PositiveIntegerField(null=True, blank=True)

    # ── Language + nativity ──────────────────────────────────────────────
    pop_5_17_english_at_home = models.PositiveIntegerField(null=True, blank=True)
    pop_5_17_other_lang_at_home = models.PositiveIntegerField(null=True, blank=True)
    pop_5_17_foreign_born = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "sw_civic_nces_edge_demographics"
        verbose_name = "NCES EDGE District Demographics"
        unique_together = [["vintage", "geoid"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["state_fips", "vintage"]),
        ]

    def __str__(self):
        return (
            f"EDGE demographics {self.geoid} @ {self.vintage.name} "
            f"(pop_5_17={self.population_5_17})"
        )
