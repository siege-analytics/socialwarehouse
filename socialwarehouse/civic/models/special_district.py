"""Census special-district attribute records.

F Phase 2 (SW#194): per maintainer's call (2026-05-20 thread): ship
the warehouse-side schema now so the FEC analysis project has a place
to write attributes against; defer auto-ingest from the Census of
Governments (COG) file until a real consumer surfaces with format
requirements.

Boundary geometry + canonical names live upstream in siege_utilities
per-kind special-district models (FireDistrict, WaterDistrict, ...)
delivered by C / SU#535. This table adds the COG-style attributes on
top: governing body, annual revenue, source URL, source year.

Long-format keying — `(boundary_type, geoid, source_year)` — matches
the cross-source pattern used by ACSEstimate, BLSQCEWAggregate, and
IRSSOIAggregate. The `boundary_type` discriminator carries the per-
kind value (one of `_SPECIAL_DISTRICT_BOUNDARY_TYPES`) so a single
table can serve every special-district subkind C ships.
"""

from django.db import models


# The set of special-district boundary types that this table can carry
# attributes for. Matches Address._BOUNDARY_TYPES special-district
# entries and SU#535's per-kind models.
_SPECIAL_DISTRICT_BOUNDARY_TYPES = (
    "fire_district",
    "water_district",
    "hospital_district",
    "library_district",
    "cemetery_district",
    "mosquito_district",
    "other_special_district",
)

BOUNDARY_TYPE_CHOICES = [(t, t) for t in _SPECIAL_DISTRICT_BOUNDARY_TYPES]


class SpecialDistrictAttributes(models.Model):
    """COG-style attributes for one Census special district.

    No auto-ingest shipped — populate via your own loader (manual
    fixture, COG file parser, FEC project, etc.). The unique key
    `(boundary_type, geoid, source_year)` lets a single district
    carry multiple years of attribute history.
    """

    boundary_type = models.CharField(
        max_length=30,
        db_index=True,
        choices=BOUNDARY_TYPE_CHOICES,
        help_text=(
            "Special-district kind. Must match one of SW's special-"
            "district boundary types (matches SU#535's per-kind models)."
        ),
    )
    geoid = models.CharField(
        max_length=20,
        db_index=True,
        help_text="TIGER GEOID for the district's boundary row.",
    )
    source_year = models.PositiveSmallIntegerField(
        db_index=True,
        help_text=(
            "Year the attribute snapshot applies to. Census of "
            "Governments runs every 5 years (2017, 2022, ...); a one-"
            "off custom load might use any year. Required for the "
            "unique-together key so multiple snapshots can coexist."
        ),
    )

    function = models.CharField(
        max_length=80, blank=True, default="",
        help_text=(
            "Census COG `function` description, e.g. 'Fire Protection', "
            "'Water Supply'. Free-text; not validated against a fixed "
            "set because COG categories shift release-to-release."
        ),
    )
    governing_body = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Name of the governing board / commission / authority.",
    )
    annual_revenue = models.BigIntegerField(
        null=True, blank=True,
        help_text="Annual revenue in whole dollars; nullable when unreported.",
    )
    source_url = models.URLField(
        blank=True, default="",
        help_text=(
            "URL the attributes were sourced from (COG release page, "
            "state register, district's own site)."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sw_civic_special_district_attributes"
        verbose_name = "Special District Attributes"
        verbose_name_plural = "Special District Attributes"
        unique_together = [["boundary_type", "geoid", "source_year"]]
        indexes = [
            models.Index(fields=["boundary_type", "source_year"]),
        ]
        ordering = ["boundary_type", "geoid", "source_year"]

    def __str__(self):
        return f"{self.boundary_type}:{self.geoid} ({self.source_year})"
