"""Polymorphic Vintage models.

Template-readiness B (SW#190): replaces the single-table
`CensusVintageConfig` assumption with a concept that accommodates the
temporal shapes of every data domain the template ships.

Shape decision (per design v2, PR #199): **Shape A2 — Django
multi-table inheritance**. A concrete `Vintage` parent table carries
the fields every kind needs (`name`, `effective_from`,
`effective_to`, `kind`, `created_at`). Per-kind subclasses
(`CensusDecadalVintage`, `ACSVintage`, ...) carry their type-safe
extras and get their own backing tables with a 1:1 FK back to the
parent.

Downstream consumers FK the parent (`Vintage`); they read flat
`effective_from / effective_to` columns directly. Kind-specific
fields are accessible via the subclass downcast accessor
(`vintage.acsvintage.span_years`, etc.).

This module ships as part of B-PR-1 (additive only — does not touch
ABP's existing `vintage` FK). B-PR-2 retargets ABP and drops
`CensusVintageConfig`.
"""

from django.db import models


# Kind strings; subclass `save()` methods set these on the parent
# automatically so callers don't have to.
KIND_CENSUS_DECADAL = "census-decadal"
KIND_ACS = "acs"
KIND_BLS_QCEW = "bls-qcew"
KIND_BEA_REGIONAL = "bea-regional"
KIND_NCES_SCHOOL_YEAR = "nces-school-year"
KIND_REDISTRICTING_PLAN = "redistricting-plan"

KIND_CHOICES = [
    (KIND_CENSUS_DECADAL, "Decennial Census"),
    (KIND_ACS, "American Community Survey"),
    (KIND_BLS_QCEW, "BLS Quarterly Census of Employment and Wages"),
    (KIND_BEA_REGIONAL, "BEA Regional"),
    (KIND_NCES_SCHOOL_YEAR, "NCES School Year"),
    (KIND_REDISTRICTING_PLAN, "Redistricting Plan"),
]


class Vintage(models.Model):
    """Concrete parent for all temporal-period concepts.

    Carries shared fields. Per-kind subclasses inherit via Django
    multi-table inheritance and add their kind-specific fields.
    Queries against `Vintage` return parent rows; downcast via the
    subclass attribute accessor (e.g., `v.acsvintage.span_years`).
    """

    name = models.CharField(
        max_length=100,
        db_index=True,
        help_text=(
            "Human-readable identifier for this vintage. Format conventions "
            "per kind; e.g. '2020' for census-decadal, '2019-2023' for "
            "acs-5year, '2024Q3' for bls-qcew."
        ),
    )
    kind = models.CharField(
        max_length=30,
        choices=KIND_CHOICES,
        db_index=True,
        help_text=(
            "Discriminator. Set automatically by each subclass's save() "
            "method; downstream code can filter by kind without downcasting."
        ),
    )
    effective_from = models.DateField(
        db_index=True,
        help_text="Date the vintage's data became current / authoritative.",
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Date the vintage was superseded; NULL = unreplaced / "
            "currently in effect. Set by the `seal_superseded_vintages` "
            "management command when a newer vintage of the same kind lands."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sw_geo_vintage"
        ordering = ["kind", "-effective_from"]
        indexes = [
            models.Index(fields=["kind", "effective_to"]),
            models.Index(fields=["effective_from", "effective_to"]),
        ]

    def __str__(self):
        return f"{self.kind}:{self.name}"

    def is_current(self, on_date=None):
        """True if this vintage's window contains `on_date` (default: today)."""
        from datetime import date as _date

        on_date = on_date or _date.today()
        if self.effective_from and self.effective_from > on_date:
            return False
        if self.effective_to is not None and self.effective_to <= on_date:
            return False
        return True


class CensusDecadalVintageManager(models.Manager):
    """Custom manager carrying the legacy `for_year` lookup.

    Preserves the `CensusVintageConfig.for_year(year)` API surface that
    F11's helpers and `assign_boundaries` already depend on, but
    resolves through the polymorphic Vintage table.
    """

    def for_year(self, year):
        """Return the CensusDecadalVintage whose decade covers `year`.

        2026 → decade 2020; 2018 → decade 2010; etc. Returns None for
        years before any seeded decade.
        """
        decade = (year // 10) * 10
        return self.filter(decade=decade).first()


class CensusDecadalVintage(Vintage):
    """Decennial Census vintage (2010, 2020, ...).

    A new row is created each decade; the previous decade's vintage
    gets `effective_to` set when the new one lands.
    """

    decade = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Decade marker year, e.g. 2010, 2020, 2030.",
    )

    objects = CensusDecadalVintageManager()

    class Meta:
        db_table = "sw_geo_vintage_census_decadal"
        verbose_name = "Census Decadal Vintage"

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = KIND_CENSUS_DECADAL
        if not self.name:
            self.name = str(self.decade)
        super().save(*args, **kwargs)


class ACSVintage(Vintage):
    """American Community Survey vintage.

    Carries `start_year`, `end_year`, and `span_years`. For 1-year ACS,
    start_year == end_year. For 5-year ACS, end_year = start_year + 4.
    """

    SPAN_1YEAR = 1
    SPAN_5YEAR = 5
    SPAN_CHOICES = [
        (SPAN_1YEAR, "1-year"),
        (SPAN_5YEAR, "5-year"),
    ]

    start_year = models.PositiveSmallIntegerField()
    end_year = models.PositiveSmallIntegerField()
    span_years = models.PositiveSmallIntegerField(choices=SPAN_CHOICES)

    class Meta:
        db_table = "sw_geo_vintage_acs"
        verbose_name = "ACS Vintage"
        unique_together = [["start_year", "end_year", "span_years"]]

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = KIND_ACS
        if not self.name:
            if self.span_years == self.SPAN_1YEAR:
                self.name = f"{self.start_year}"
            else:
                self.name = f"{self.start_year}-{self.end_year}"
        super().save(*args, **kwargs)


class BLSQCEWVintage(Vintage):
    """BLS Quarterly Census of Employment and Wages vintage."""

    year = models.PositiveSmallIntegerField()
    quarter = models.PositiveSmallIntegerField(
        choices=[(1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4")],
    )

    class Meta:
        db_table = "sw_geo_vintage_bls_qcew"
        verbose_name = "BLS QCEW Vintage"
        unique_together = [["year", "quarter"]]

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = KIND_BLS_QCEW
        if not self.name:
            self.name = f"{self.year}Q{self.quarter}"
        super().save(*args, **kwargs)


class BEARegionalVintage(Vintage):
    """BEA Regional Economic Accounts vintage. Annual."""

    year = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        db_table = "sw_geo_vintage_bea_regional"
        verbose_name = "BEA Regional Vintage"

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = KIND_BEA_REGIONAL
        if not self.name:
            self.name = str(self.year)
        super().save(*args, **kwargs)


class NCESSchoolYearVintage(Vintage):
    """NCES school-year vintage. Each row spans two calendar years
    (e.g., 2023-24 = academic year starting Aug 2023, ending May 2024).
    """

    start_year = models.PositiveSmallIntegerField()
    end_year = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "sw_geo_vintage_nces_school_year"
        verbose_name = "NCES School Year Vintage"
        unique_together = [["start_year", "end_year"]]

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = KIND_NCES_SCHOOL_YEAR
        if not self.name:
            self.name = f"{self.start_year}-{str(self.end_year)[-2:]}"
        super().save(*args, **kwargs)


class RedistrictingPlanVintage(Vintage):
    """Vintage corresponding to a single siege_utilities.RedistrictingPlan.

    `effective_from` / `effective_to` track the plan's lifecycle as
    reflected in the upstream plan's `effective_from` / `effective_to`
    columns (added in SU#528).
    """

    siege_redistricting_plan_id = models.PositiveBigIntegerField(
        unique=True,
        help_text=(
            "FK-like reference to siege_utilities RedistrictingPlan.id. "
            "Not a Django FK because siege_geo is a separate app whose "
            "migrations evolve independently; use the id-based lookup "
            "pattern (RedistrictingPlan.objects.filter(pk=...))."
        ),
    )
    state_fips = models.CharField(max_length=2, db_index=True)
    chamber = models.CharField(max_length=20, db_index=True)
    plan_name = models.CharField(max_length=255)

    class Meta:
        db_table = "sw_geo_vintage_redistricting_plan"
        verbose_name = "Redistricting Plan Vintage"

    def save(self, *args, **kwargs):
        if not self.kind:
            self.kind = KIND_REDISTRICTING_PLAN
        if not self.name:
            self.name = self.plan_name
        super().save(*args, **kwargs)
