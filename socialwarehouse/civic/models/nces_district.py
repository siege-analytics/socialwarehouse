"""NCES CCD district-level aggregate (per-LEA per-school-year).

Per F design (#210): Q1 = (b) CCD + EDGE both; Q2 = (b) district +
school level. This is the district half of Phase 1; school-level
is Phase 1b; EDGE demographic estimates per district are Phase 1c.

Per F Q4 = (b) all line items: this model carries the full NCES F-33
finance breakdown, not just three rollups.

One row per (vintage, geoid). vintage is an NCESSchoolYearVintage row;
geoid is the 7-digit LEAID.
"""

from django.db import models


class NCESDistrictAggregate(models.Model):
    """One row per LEA per school year."""

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="nces_district_aggregates",
        limit_choices_to={"kind": "nces-school-year"},
        help_text="Polymorphic Vintage parent; should be an NCESSchoolYearVintage row.",
    )
    boundary_type = models.CharField(
        max_length=30, default="school_district", db_index=True,
        help_text="Always 'school_district' for this model; field kept for D/E/F shape consistency.",
    )
    geoid = models.CharField(
        max_length=7, db_index=True,
        help_text="NCES LEAID (7-digit Local Education Agency ID).",
    )

    # ── Directory ────────────────────────────────────────────────────────
    district_type = models.CharField(
        max_length=20, blank=True, default="",
        choices=[
            ("unified", "Unified (K-12)"),
            ("elementary", "Elementary only"),
            ("secondary", "Secondary only"),
            ("other", "Other (charter, special, supervisory union)"),
        ],
        help_text="NCES agency-type classification.",
    )
    state_fips = models.CharField(max_length=2, blank=True, default="", db_index=True)

    # ── Enrollment + staff (CCD nonfiscal) ───────────────────────────────
    enrollment_total = models.PositiveIntegerField(null=True, blank=True)
    enrollment_pk_grade_k = models.PositiveIntegerField(null=True, blank=True)
    enrollment_grade_1_5 = models.PositiveIntegerField(null=True, blank=True)
    enrollment_grade_6_8 = models.PositiveIntegerField(null=True, blank=True)
    enrollment_grade_9_12 = models.PositiveIntegerField(null=True, blank=True)
    free_lunch_eligible_count = models.PositiveIntegerField(null=True, blank=True)
    reduced_lunch_eligible_count = models.PositiveIntegerField(null=True, blank=True)
    title_i_eligible = models.BooleanField(null=True, blank=True)

    teachers_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    instructional_aides_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    administrators_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    instructional_coordinators_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    support_staff_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # ── Finance (CCD F-33, per F Q4 = all line items) ────────────────────
    revenue_total = models.BigIntegerField(null=True, blank=True)
    revenue_federal = models.BigIntegerField(null=True, blank=True)
    revenue_federal_title_i = models.BigIntegerField(null=True, blank=True)
    revenue_federal_idea = models.BigIntegerField(null=True, blank=True)
    revenue_federal_child_nutrition = models.BigIntegerField(null=True, blank=True)
    revenue_state = models.BigIntegerField(null=True, blank=True)
    revenue_state_formula = models.BigIntegerField(null=True, blank=True)
    revenue_state_compensatory = models.BigIntegerField(null=True, blank=True)
    revenue_state_special_ed = models.BigIntegerField(null=True, blank=True)
    revenue_local = models.BigIntegerField(null=True, blank=True)
    revenue_local_property_tax = models.BigIntegerField(null=True, blank=True)
    revenue_local_parent_govt = models.BigIntegerField(null=True, blank=True)

    expenditure_total = models.BigIntegerField(null=True, blank=True)
    expenditure_instruction = models.BigIntegerField(null=True, blank=True)
    expenditure_support_services = models.BigIntegerField(null=True, blank=True)
    expenditure_food_services = models.BigIntegerField(null=True, blank=True)
    expenditure_capital_outlay = models.BigIntegerField(null=True, blank=True)
    expenditure_per_pupil = models.PositiveIntegerField(null=True, blank=True)

    long_term_debt_outstanding = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "sw_civic_nces_district_aggregate"
        verbose_name = "NCES District Aggregate"
        unique_together = [["vintage", "geoid"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["state_fips", "vintage"]),
        ]

    def __str__(self):
        return f"NCES district {self.geoid} @ {self.vintage.name} (enrollment={self.enrollment_total})"
