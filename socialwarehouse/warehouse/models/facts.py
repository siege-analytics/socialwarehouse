"""
Warehouse fact tables for longitudinal Census and civic analysis.

Each fact table links to dimension tables via foreign keys and stores
measured values. Designed for analytical queries (aggregations, time-series,
cross-tabulations).

Note: Domain-specific facts (e.g., FEC donation summaries) belong in the
consuming application (pure-translation), not here.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .dimensions import (
    DimCensusVariable,
    DimGeography,
    DimRedistrictingCycle,
    DimSurvey,
    DimTime,
)


class FactACSEstimate(models.Model):
    """ACS estimate fact — one row per (geography, variable, survey)."""

    RELIABILITY_CHOICES = [
        ("high", "High (CV < 12%)"),
        ("medium", "Medium (CV 12-40%)"),
        ("low", "Low (CV > 40%)"),
        ("suppressed", "Suppressed by Census Bureau"),
    ]

    geography = models.ForeignKey(DimGeography, on_delete=models.CASCADE, related_name="acs_estimates")
    variable = models.ForeignKey(DimCensusVariable, on_delete=models.CASCADE, related_name="acs_estimates")
    survey = models.ForeignKey(DimSurvey, on_delete=models.CASCADE, related_name="acs_estimates")
    estimate = models.FloatField()
    margin_of_error = models.FloatField(null=True, blank=True)
    coefficient_of_variation = models.FloatField(null=True, blank=True)
    reliability = models.CharField(max_length=10, choices=RELIABILITY_CHOICES, default="medium")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_acs_estimate"
        verbose_name = "ACS Estimate"
        unique_together = [("geography", "variable", "survey")]
        indexes = [
            models.Index(fields=["geography", "survey"]),
            models.Index(fields=["variable", "survey"]),
            models.Index(fields=["reliability"]),
        ]

    def __str__(self):
        return f"{self.variable.variable_code} @ {self.geography.geoid}: {self.estimate}"

    def compute_reliability(self):
        if self.coefficient_of_variation is None:
            return "suppressed"
        cv = abs(self.coefficient_of_variation)
        if cv < 12:
            return "high"
        if cv < 40:
            return "medium"
        return "low"

    def save(self, *args, **kwargs):
        if self.margin_of_error is not None and self.estimate and self.estimate != 0:
            se = abs(self.margin_of_error) / 1.645
            self.coefficient_of_variation = (se / abs(self.estimate)) * 100
        self.reliability = self.compute_reliability()
        super().save(*args, **kwargs)


class FactDecennialCount(models.Model):
    """Decennial Census count fact — 100% enumeration, no sampling error."""

    geography = models.ForeignKey(DimGeography, on_delete=models.CASCADE, related_name="decennial_counts")
    variable = models.ForeignKey(DimCensusVariable, on_delete=models.CASCADE, related_name="decennial_counts")
    survey = models.ForeignKey(DimSurvey, on_delete=models.CASCADE, related_name="decennial_counts")
    count = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_decennial_count"
        verbose_name = "Decennial Count"
        unique_together = [("geography", "variable", "survey")]
        indexes = [
            models.Index(fields=["geography", "survey"]),
            models.Index(fields=["variable", "survey"]),
        ]

    def __str__(self):
        return f"{self.variable.variable_code} @ {self.geography.geoid}: {self.count}"


class FactUrbanicity(models.Model):
    """Urbanicity fact — NCES locale classification per geography."""

    METHOD_CHOICES = [
        ("direct", "Direct NCES assignment"),
        ("overlay", "Spatial overlay of NCES locale boundaries"),
        ("majority", "Majority locale code from area-weighted overlay"),
    ]

    geography = models.ForeignKey(DimGeography, on_delete=models.CASCADE, related_name="urbanicity_facts")
    nces_year = models.PositiveSmallIntegerField()
    locale_code = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(11), MaxValueValidator(43)],
    )
    locale_category = models.CharField(max_length=20)
    locale_subcategory = models.CharField(max_length=30, blank=True, default="")
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="overlay")
    confidence = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_urbanicity"
        verbose_name = "Urbanicity Fact"
        unique_together = [("geography", "nces_year", "method")]
        indexes = [
            models.Index(fields=["locale_code"]),
            models.Index(fields=["locale_category"]),
        ]

    def __str__(self):
        return f"{self.geography.geoid}: {self.locale_category} ({self.locale_code})"


class FactElectionResult(models.Model):
    """Election result fact — vote tallies by geography."""

    OFFICE_CHOICES = [
        ("president", "President"),
        ("senate", "U.S. Senate"),
        ("house", "U.S. House"),
        ("governor", "Governor"),
        ("state_senate", "State Senate"),
        ("state_house", "State House"),
    ]

    geography = models.ForeignKey(DimGeography, on_delete=models.CASCADE, related_name="election_results")
    election_date = models.ForeignKey(DimTime, on_delete=models.CASCADE, related_name="election_results")
    office = models.CharField(max_length=20, choices=OFFICE_CHOICES)
    party = models.CharField(max_length=50)
    candidate_name = models.CharField(max_length=255, blank=True, default="")
    votes = models.IntegerField()
    total_votes = models.IntegerField(null=True, blank=True)
    vote_share = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_election_result"
        verbose_name = "Election Result"
        unique_together = [("geography", "election_date", "office", "party", "candidate_name")]
        indexes = [
            models.Index(fields=["geography", "election_date", "office"]),
            models.Index(fields=["office", "party"]),
        ]

    def __str__(self):
        return f"{self.office} {self.party}: {self.votes} @ {self.geography.geoid}"


class FactPrecinctResult(models.Model):
    """Precinct-level election result fact from RDH data."""

    OFFICE_CHOICES = [
        ("president", "President"),
        ("senate", "U.S. Senate"),
        ("house", "U.S. House"),
        ("governor", "Governor"),
        ("state_senate", "State Senate"),
        ("state_house", "State House"),
        ("attorney_general", "Attorney General"),
        ("secretary_of_state", "Secretary of State"),
    ]

    geography = models.ForeignKey(DimGeography, on_delete=models.CASCADE, related_name="precinct_results")
    election_date = models.ForeignKey(DimTime, on_delete=models.CASCADE, related_name="precinct_results")
    office = models.CharField(max_length=30, choices=OFFICE_CHOICES)
    party = models.CharField(max_length=50)
    candidate_name = models.CharField(max_length=255, blank=True, default="")
    votes = models.IntegerField()
    total_votes = models.IntegerField(null=True, blank=True)
    vote_share = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_precinct_result"
        verbose_name = "Precinct Result"
        unique_together = [("geography", "election_date", "office", "party", "candidate_name")]
        indexes = [
            models.Index(fields=["geography", "election_date", "office"]),
            models.Index(fields=["office", "party"]),
        ]

    def __str__(self):
        return f"{self.office} {self.party}: {self.votes} @ {self.geography.geoid}"


class FactRedistrictingPlan(models.Model):
    """District-level redistricting plan fact with compactness scores."""

    CHAMBER_CHOICES = [
        ("congress", "U.S. Congress"),
        ("state_senate", "State Senate"),
        ("state_house", "State House"),
    ]
    PLAN_TYPE_CHOICES = [
        ("enacted", "Enacted"),
        ("proposed", "Proposed"),
        ("alternative", "Alternative"),
        ("court_ordered", "Court-Ordered"),
        ("commission", "Commission"),
    ]

    geography = models.ForeignKey(DimGeography, on_delete=models.CASCADE, related_name="redistricting_plans")
    cycle = models.ForeignKey(DimRedistrictingCycle, on_delete=models.CASCADE, related_name="plan_facts")
    chamber = models.CharField(max_length=20, choices=CHAMBER_CHOICES)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default="enacted")
    district_number = models.CharField(max_length=10)
    total_population = models.BigIntegerField(null=True, blank=True)
    vap = models.BigIntegerField(null=True, blank=True, help_text="Voting age population")
    cvap = models.BigIntegerField(null=True, blank=True, help_text="Citizen voting age population")
    deviation_pct = models.FloatField(null=True, blank=True)
    polsby_popper = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    reock = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_redistricting_plan"
        verbose_name = "Redistricting Plan Fact"
        indexes = [
            models.Index(fields=["geography", "cycle"]),
            models.Index(fields=["cycle", "chamber"]),
        ]

    def __str__(self):
        return f"{self.chamber} District {self.district_number} ({self.cycle.cycle_year})"
