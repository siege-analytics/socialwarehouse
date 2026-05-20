"""NCES CCD school-level aggregate (per-school per-school-year).

Per F design (#210) Q2 = (b) district + school level. Phase 1a
shipped the district half (NCESDistrictAggregate); this is the
school half.

NCES School ID is 12 digits: 7-digit LEAID + 5-digit school sequence.
"""

from django.db import models


class NCESSchoolAggregate(models.Model):
    """One row per NCES school per school year."""

    vintage = models.ForeignKey(
        "sw_geo.Vintage",
        on_delete=models.CASCADE,
        related_name="nces_school_aggregates",
        limit_choices_to={"kind": "nces-school-year"},
        help_text="Polymorphic Vintage parent; should be an NCESSchoolYearVintage row.",
    )
    boundary_type = models.CharField(
        max_length=30, default="school", db_index=True,
        help_text="'school' for this model; kept for D/E/F shape consistency.",
    )
    geoid = models.CharField(
        max_length=12, db_index=True,
        help_text="NCES School ID (12-digit; LEAID prefix + 5-digit school sequence).",
    )
    leaid = models.CharField(
        max_length=7, db_index=True,
        help_text="Parent LEA (district) ID; joins to NCESDistrictAggregate.geoid.",
    )
    state_fips = models.CharField(max_length=2, blank=True, default="", db_index=True)

    # ── Directory ────────────────────────────────────────────────────────
    school_name = models.CharField(max_length=255, blank=True, default="")
    school_type = models.CharField(
        max_length=20, blank=True, default="",
        choices=[
            ("regular", "Regular school"),
            ("special", "Special education school"),
            ("vocational", "Vocational school"),
            ("alternative", "Alternative school"),
            ("other", "Other"),
        ],
    )
    school_status = models.CharField(
        max_length=20, blank=True, default="",
        choices=[
            ("open", "Open"),
            ("closed", "Closed"),
            ("new", "New school"),
            ("added", "Added to NCES universe"),
            ("changed_boundary", "Boundary change"),
            ("inactive", "Inactive"),
            ("future", "Future open date"),
            ("reopened", "Reopened"),
        ],
    )
    is_charter = models.BooleanField(null=True, blank=True)
    is_magnet = models.BooleanField(null=True, blank=True)
    is_title_i = models.BooleanField(null=True, blank=True)
    grade_low = models.CharField(max_length=4, blank=True, default="")
    grade_high = models.CharField(max_length=4, blank=True, default="")

    # ── Enrollment (CCD school-level nonfiscal) ──────────────────────────
    enrollment_total = models.PositiveIntegerField(null=True, blank=True)
    enrollment_pk_grade_k = models.PositiveIntegerField(null=True, blank=True)
    enrollment_grade_1_5 = models.PositiveIntegerField(null=True, blank=True)
    enrollment_grade_6_8 = models.PositiveIntegerField(null=True, blank=True)
    enrollment_grade_9_12 = models.PositiveIntegerField(null=True, blank=True)
    free_lunch_eligible_count = models.PositiveIntegerField(null=True, blank=True)
    reduced_lunch_eligible_count = models.PositiveIntegerField(null=True, blank=True)
    teachers_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "sw_civic_nces_school_aggregate"
        verbose_name = "NCES School Aggregate"
        unique_together = [["vintage", "geoid"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["leaid", "vintage"]),
            models.Index(fields=["state_fips", "vintage"]),
        ]

    def __str__(self):
        return (
            f"NCES school {self.geoid} ({self.school_name or '?'}) @ "
            f"{self.vintage.name} (enrollment={self.enrollment_total})"
        )
