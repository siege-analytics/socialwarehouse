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
    VENDOR_CHOICES,
    DimCensusVariable,
    DimGeography,
    DimPerson,
    DimRedistrictingCycle,
    DimSurvey,
    DimTime,
)


ELECTION_TYPE_CHOICES = [
    ("general", "General"),
    ("primary", "Primary"),
    ("runoff", "Runoff"),
    ("special", "Special"),
    ("local", "Local"),
    ("other", "Other"),
]


VOTED_METHOD_CHOICES = [
    ("in_person", "In person"),
    ("absentee", "Absentee"),
    ("mail", "Mail"),
    ("early", "Early"),
    ("provisional", "Provisional"),
    ("unknown", "Unknown"),
]


# Census Bureau coefficient-of-variation reliability thresholds. Drawn
# from Census's published guidance for ACS estimate reliability: CV < 12%
# = high reliability, 12-40% = medium, > 40% = low. Hoisted to module
# scope so the RELIABILITY_CHOICES strings, the compute_reliability
# implementation, and any downstream analytics that want to mirror these
# bands share one source of truth. (W4 / SW#108)
CV_HIGH_THRESHOLD = 12
CV_MEDIUM_THRESHOLD = 40


class FactACSEstimate(models.Model):
    """ACS estimate fact — one row per (geography, variable, survey)."""

    RELIABILITY_CHOICES = [
        ("high", f"High (CV < {CV_HIGH_THRESHOLD}%)"),
        ("medium", f"Medium (CV {CV_HIGH_THRESHOLD}-{CV_MEDIUM_THRESHOLD}%)"),
        ("low", f"Low (CV > {CV_MEDIUM_THRESHOLD}%)"),
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
        if cv < CV_HIGH_THRESHOLD:
            return "high"
        if cv < CV_MEDIUM_THRESHOLD:
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
    electoral_contest = models.ForeignKey(
        "sw_political.ElectoralContest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="election_results",
    )
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
            models.Index(fields=["electoral_contest"], name="idx_fer_contest"),
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
    electoral_contest = models.ForeignKey(
        "sw_political.ElectoralContest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="precinct_results",
    )
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
            models.Index(fields=["electoral_contest"], name="idx_fpr_contest"),
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
        unique_together = [("geography", "cycle", "chamber", "plan_type", "district_number")]
        indexes = [
            models.Index(fields=["geography", "cycle"]),
            models.Index(fields=["cycle", "chamber"]),
        ]

    def __str__(self):
        return f"{self.chamber} District {self.district_number} ({self.cycle.cycle_year})"


class FactPersonScore(models.Model):
    """Per-person score event (partisan, turnout propensity, issue stance, etc.).

    Tall format: one row per (person, score_type, source_vendor,
    methodology_version). Vendor scoring systems are NOT interchangeable
    even when score_type matches — each score carries its source_vendor
    and methodology_version. Consumers querying "give me a partisan
    score" must pick a source explicitly.

    `score_type` is a free string (not a choices enum). Vendor scoring
    vocabularies grow over time; a migration-per-cycle is not viable.
    Common types: 'partisan_score', 'turnout_propensity_general',
    'turnout_propensity_primary', 'issue_<topic>'. See
    docs/entities/fact-person-score.md for the registered vocabulary.
    """

    person = models.ForeignKey(DimPerson, on_delete=models.CASCADE, related_name="scores")
    score_type = models.CharField(max_length=128, db_index=True)
    value = models.FloatField()
    source_vendor = models.CharField(max_length=16, choices=VENDOR_CHOICES)
    methodology_version = models.CharField(max_length=64, blank=True, default="")
    scored_at = models.DateTimeField()
    loaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_person_score"
        verbose_name = "Person Score Fact"
        verbose_name_plural = "Person Score Facts"
        unique_together = [("person", "score_type", "source_vendor", "methodology_version")]
        indexes = [
            models.Index(fields=["score_type", "source_vendor"]),
            models.Index(fields=["person", "score_type"]),
        ]

    def __str__(self):
        return f"{self.score_type}={self.value} ({self.source_vendor}) for {self.person_id}"


class FactVoteHistory(models.Model):
    """Per-person per-election vote event.

    `unique_together` on (person, election_date, election_type,
    source_vendor) preserves both vendors' reports of the same vote
    while preventing duplicate-load. Cross-vendor reconciliation
    (when two vendors disagree on voted_method) is a consumer
    decision; both rows are kept.
    """

    person = models.ForeignKey(DimPerson, on_delete=models.CASCADE, related_name="vote_history")
    election_date = models.DateField(db_index=True)
    election_type = models.CharField(max_length=16, choices=ELECTION_TYPE_CHOICES)
    voted_method = models.CharField(max_length=16, choices=VOTED_METHOD_CHOICES, default="unknown")
    source_vendor = models.CharField(max_length=16, choices=VENDOR_CHOICES)
    loaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_fact_vote_history"
        verbose_name = "Vote History Fact"
        verbose_name_plural = "Vote History Facts"
        unique_together = [("person", "election_date", "election_type", "source_vendor")]
        indexes = [
            models.Index(fields=["person", "election_date"]),
            models.Index(fields=["election_date", "election_type"]),
        ]

    def __str__(self):
        return f"{self.election_type} {self.election_date} ({self.source_vendor}) for {self.person_id}"
