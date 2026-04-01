"""
Warehouse dimension tables for longitudinal Census analysis.

Implements a star-schema design with SCD Type 2 geography dimension
and standard dimensions for survey, variable, and time.
"""

from django.contrib.gis.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


class DimGeography(models.Model):
    """Geography dimension with SCD Type 2 for boundary changes over time.

    Natural key: (geoid, vintage_year).
    Surrogate PK: auto-incremented BigAutoField.

    Supports drill-up via the parent FK (tract → county → state).
    """

    geoid = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Census GEOID (e.g. '06037' for LA County)",
    )
    name = models.CharField(max_length=255)
    vintage_year = models.PositiveSmallIntegerField(
        db_index=True,
        validators=[MinValueValidator(1790), MaxValueValidator(2100)],
        help_text="TIGER/Line vintage year for this boundary shape",
    )
    summary_level = models.CharField(
        max_length=30,
        db_index=True,
        help_text="Geography type (state, county, tract, blockgroup, place, cd, zcta)",
    )
    state_fips = models.CharField(
        max_length=2,
        blank=True,
        default="",
        db_index=True,
    )
    geometry = models.MultiPolygonField(
        srid=4326,
        null=True,
        blank=True,
        help_text="Boundary geometry (WGS 84) — nullable for lightweight loads",
    )
    area_land = models.BigIntegerField(null=True, blank=True, help_text="Sq meters")
    area_water = models.BigIntegerField(null=True, blank=True, help_text="Sq meters")
    internal_point = models.PointField(
        srid=4326,
        null=True,
        blank=True,
        help_text="Interior label point",
    )

    # SCD Type 2 fields
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent geography for drill-up (tract→county→state)",
    )
    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text="Start of this version's validity period",
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text="End of this version's validity (NULL = current)",
    )
    is_current = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True for the latest version of this geography",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Geography Dimension"
        verbose_name_plural = "Geography Dimensions"
        unique_together = [("geoid", "vintage_year")]
        indexes = [
            models.Index(fields=["summary_level", "vintage_year"]),
            models.Index(fields=["state_fips", "summary_level"]),
            models.Index(fields=["is_current", "summary_level"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.geoid}, {self.vintage_year})"


class DimSurvey(models.Model):
    """Survey dimension — identifies which Census program produced the data.

    One row per (survey_type, vintage_year) combination.
    """

    SURVEY_TYPES = [
        ("acs5", "ACS 5-Year Estimates"),
        ("acs1", "ACS 1-Year Estimates"),
        ("decennial", "Decennial Census"),
        ("decennial_pl", "Decennial PL 94-171"),
    ]

    survey_type = models.CharField(
        max_length=20,
        choices=SURVEY_TYPES,
        help_text="Census program type",
    )
    vintage_year = models.PositiveSmallIntegerField(
        help_text="Publication/release year of this survey",
    )
    period_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start of data collection period",
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        help_text="End of data collection period",
    )
    description = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Survey Dimension"
        verbose_name_plural = "Survey Dimensions"
        unique_together = [("survey_type", "vintage_year")]

    def __str__(self):
        return f"{self.get_survey_type_display()} {self.vintage_year}"


class DimCensusVariable(models.Model):
    """Census variable dimension — metadata about each measured variable.

    Maps Census API variable codes (e.g. B01001_001E) to human-readable
    labels and concepts.
    """

    VARIABLE_TYPES = [
        ("extensive", "Extensive (counts, totals — can be summed)"),
        ("intensive", "Intensive (rates, medians — cannot be summed)"),
    ]

    table_id = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Census table ID (e.g. B01001)",
    )
    variable_code = models.CharField(
        max_length=30,
        db_index=True,
        help_text="Full variable code (e.g. B01001_001E)",
    )
    label = models.TextField(
        help_text="Human-readable variable label",
    )
    concept = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Broader concept group (e.g. 'SEX BY AGE')",
    )
    variable_type = models.CharField(
        max_length=15,
        choices=VARIABLE_TYPES,
        default="extensive",
        help_text="Whether this variable can be aggregated by summing",
    )
    dataset = models.CharField(
        max_length=20,
        default="acs5",
        help_text="Census dataset this variable belongs to",
    )
    universe = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Statistical universe (e.g. 'Total population')",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Census Variable Dimension"
        verbose_name_plural = "Census Variable Dimensions"
        unique_together = [("variable_code", "dataset")]
        indexes = [
            models.Index(fields=["table_id"]),
        ]

    def __str__(self):
        return f"{self.variable_code}: {self.label[:60]}"

    @property
    def is_estimate(self) -> bool:
        return self.variable_code.endswith("E")

    @property
    def is_moe(self) -> bool:
        return self.variable_code.endswith("M")


class DimTime(models.Model):
    """Time dimension — calendar dates with Census-relevant flags.

    Pre-populated with dates covering Census decades. Supports joining
    fact tables to calendar attributes without date functions in queries.
    """

    calendar_date = models.DateField(
        unique=True,
        help_text="The calendar date",
    )
    year = models.PositiveSmallIntegerField(db_index=True)
    quarter = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
    )
    month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    day_of_year = models.PositiveSmallIntegerField()
    is_census_day = models.BooleanField(
        default=False,
        help_text="True on April 1 of decennial Census years (2000, 2010, 2020)",
    )
    is_election_day = models.BooleanField(
        default=False,
        help_text="True on the first Tuesday after first Monday in November",
    )
    fiscal_year = models.PositiveSmallIntegerField(
        help_text="Federal fiscal year (Oct-Sep)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Time Dimension"
        verbose_name_plural = "Time Dimensions"
        indexes = [
            models.Index(fields=["year", "quarter"]),
            models.Index(fields=["is_census_day"]),
            models.Index(fields=["is_election_day"]),
        ]

    def __str__(self):
        return str(self.calendar_date)


class DimRedistrictingCycle(models.Model):
    """Redistricting cycle dimension.

    One row per decennial redistricting cycle. Links redistricting fact
    tables to the Census cycle that triggered the redistricting.
    """

    cycle_year = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1960), MaxValueValidator(2040)],
        help_text="Redistricting cycle year (e.g. 2010, 2020, 2030)",
    )
    decennial_census_year = models.PositiveSmallIntegerField(
        help_text="Corresponding decennial Census year",
    )
    first_election_year = models.PositiveSmallIntegerField(
        help_text="First general election under this plan",
    )
    notes = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Redistricting Cycle Dimension"
        verbose_name_plural = "Redistricting Cycle Dimensions"

    def __str__(self):
        return f"Redistricting Cycle {self.cycle_year}"
