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

    # Scope is intentionally narrow: only Census programs SW has an
    # active loader path for today. Adding a choice here requires a
    # Django migration AND a corresponding loader; adding it without
    # the loader puts a non-functional option in the admin dropdown
    # that confuses operators. Programs SW does NOT yet handle (add
    # in lockstep with their loader):
    #   - PEP (Population Estimates Program)
    #   - Economic Census (5-year)
    #   - ACS Subject Tables
    #   - CHAS (Comprehensive Housing Affordability Strategy)
    #   - American Housing Survey
    # See W5 / SW#109 for the original gap-discovery context.
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
    day_of_month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        default=1,
        help_text="Day of calendar month (1-31)",
    )
    day_of_week = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        default=0,
        help_text="Python weekday() convention: 0=Monday, 6=Sunday",
    )
    week_of_year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(53)],
        default=1,
        help_text="ISO week number (1-53)",
    )
    is_census_day = models.BooleanField(
        default=False,
        help_text="True on April 1 of decennial Census years (2000, 2010, 2020)",
    )
    is_election_day = models.BooleanField(
        default=False,
        help_text="True on the first Tuesday after first Monday in November",
    )
    is_presidential_election = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True on presidential general election day (every 4 years)",
    )
    is_midterm_election = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True on midterm general election day (every 4 years, offset from presidential)",
    )
    federal_fiscal_year = models.PositiveSmallIntegerField(
        default=0,
        help_text="Federal fiscal year (Oct-Sep). FY starts Oct 1 of (calendar_year - 1).",
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
    census_year = models.PositiveSmallIntegerField(
        default=0,
        help_text="Corresponding decennial Census year (typically equals cycle_year). 0 = unset.",
    )
    first_election_year = models.PositiveSmallIntegerField(
        default=0,
        help_text="First general election under this plan (typically cycle_year + 2). 0 = unset.",
    )
    effective_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start date of this cycle's effective period (typically Jan 1 of first_election_year)",
    )
    effective_end = models.DateField(
        null=True,
        blank=True,
        help_text="End date of effective period (typically start of next cycle's effective period)",
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


VENDOR_CHOICES = [
    ("pdi", "PDI"),
    ("l2", "L2"),
    ("catalist", "Catalist"),
    ("ts", "TargetSmart"),
]


REGISTRATION_STATUS_CHOICES = [
    ("active", "Active"),
    ("inactive", "Inactive"),
    ("purged", "Purged"),
    ("pending", "Pending"),
    ("not_registered", "Not registered"),
    ("deceased", "Deceased"),
]


class DimPerson(models.Model):
    """Person dimension — canonical voter record.

    Natural key: (vendor, vendor_voter_id). Same physical voter loaded
    from two vendors yields two DimPerson rows; cross-vendor
    probabilistic matching is a follow-on (#250 sub-issue), and the
    schema permits it via a `canonical_person_id` column addition
    later.

    Current-only (not SCD Type 2). Vendor voter files are themselves
    point-in-time snapshots; the effective-dated semantics SCD2
    captures do not apply cleanly. Historical truth lives in the
    Delta silver.persons table (append/upsert; full history preserved
    there). Promote to SCD2 if a concrete consumer asks.

    Vendor-divergent fields live in `*_extras` JSONFields. Promote a
    map key to a canonical column when a stable pattern emerges; see
    `docs/warehouse-schema-evolution.md`.
    """

    vendor = models.CharField(max_length=16, choices=VENDOR_CHOICES, db_index=True)
    vendor_voter_id = models.CharField(max_length=128, db_index=True)

    first_name = models.CharField(max_length=128, blank=True, default="")
    middle_name = models.CharField(max_length=128, blank=True, default="")
    last_name = models.CharField(max_length=128, blank=True, default="")
    name_suffix = models.CharField(max_length=32, blank=True, default="")
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=32, blank=True, default="")
    ethnicity = models.CharField(max_length=64, blank=True, default="")
    language = models.CharField(max_length=64, blank=True, default="")

    registration_status = models.CharField(
        max_length=32,
        choices=REGISTRATION_STATUS_CHOICES,
        default="not_registered",
        db_index=True,
    )
    registration_state = models.CharField(max_length=2, db_index=True)
    registration_date = models.DateField(null=True, blank=True)
    party_registration = models.CharField(max_length=64, blank=True, default="")
    voter_status_reason = models.CharField(max_length=128, blank=True, default="")

    address = models.ForeignKey(
        "geo.Address",
        on_delete=models.PROTECT,
        related_name="people",
        null=True,
        blank=True,
        help_text="Canonical address (resolved via geo pipeline). Importers that cannot resolve an address may set null; consumer policy decides.",
    )
    # Vendor-supplied raw address preserved for audit / diff trail
    # against what canonical resolution produced.
    vendor_address_line1 = models.CharField(max_length=255, blank=True, default="")
    vendor_address_line2 = models.CharField(max_length=255, blank=True, default="")
    vendor_city = models.CharField(max_length=128, blank=True, default="")
    vendor_state = models.CharField(max_length=2, blank=True, default="")
    vendor_zip = models.CharField(max_length=5, blank=True, default="")
    vendor_zip4 = models.CharField(max_length=4, blank=True, default="")
    vendor_address_supplied_at = models.DateField(null=True, blank=True)

    household_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    household_size = models.PositiveSmallIntegerField(null=True, blank=True)
    is_head_of_household = models.BooleanField(default=False)

    # Vote-history aggregates materialized from FactVoteHistory.
    # Updated by a Spark-side recompute on the silver build (not by
    # Django signal); see docs/entities/dim-person.md for cadence.
    general_election_count = models.PositiveIntegerField(default=0)
    primary_election_count = models.PositiveIntegerField(default=0)
    total_vote_count = models.PositiveIntegerField(default=0)
    last_voted_at = models.DateField(null=True, blank=True)
    vote_frequency_category = models.CharField(max_length=32, blank=True, default="")

    pdi_extras = models.JSONField(default=dict, blank=True)
    l2_extras = models.JSONField(default=dict, blank=True)
    catalist_extras = models.JSONField(default=dict, blank=True)
    ts_extras = models.JSONField(default=dict, blank=True)

    last_loaded_from_vendor = models.CharField(
        max_length=16,
        choices=VENDOR_CHOICES,
        blank=True,
        default="",
    )
    last_loaded_at = models.DateTimeField(null=True, blank=True)
    silver_source_path = models.CharField(max_length=512, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Person Dimension"
        verbose_name_plural = "Person Dimensions"
        unique_together = [("vendor", "vendor_voter_id")]
        indexes = [
            models.Index(fields=["registration_state", "registration_status"]),
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["dob"]),
        ]

    @property
    def is_registered_voter(self):
        return self.registration_status in {"active", "inactive", "pending"}

    def __str__(self):
        name = " ".join(part for part in (self.first_name, self.last_name) if part)
        return f"{name or '(no name)'} [{self.vendor}:{self.vendor_voter_id}]"
