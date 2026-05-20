"""ACS variable catalog.

Stores the published ACS variable metadata (variable code, label,
table, universe, predicate type). Pre-seedable as a fixture for the
small curated subset, or population-able from Census's variables.json
endpoint via `fetch_acs_variables` for the full ~30K catalog
(per D Q1 = (b) full catalog).
"""

from django.db import models


class ACSVariable(models.Model):
    """One row per ACS variable across all vintages.

    Variable codes are mostly stable across ACS releases (a few get
    deprecated or renamed). We keep ONE row per variable_code, with
    `last_seen_vintage` tracking the most-recent release that
    referenced it.
    """

    variable_code = models.CharField(
        max_length=20, unique=True, db_index=True,
        help_text="Census variable code, e.g. 'B01001_001E' (total population estimate).",
    )
    label = models.TextField(
        help_text="Full hierarchical label as Census publishes it.",
    )
    concept = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Human-readable table name (e.g. 'SEX BY AGE').",
    )
    table_code = models.CharField(
        max_length=20, db_index=True,
        help_text="Table prefix, e.g. 'B01001'.",
    )
    universe = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Population universe the variable measures (e.g. 'Total population').",
    )
    predicate_type = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Census-published predicateType: int / float / string.",
    )
    first_seen_vintage = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Earliest ACS vintage name we observed this variable in.",
    )
    last_seen_vintage = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Latest ACS vintage name we observed this variable in.",
    )

    class Meta:
        db_table = "sw_demographic_acs_variable"
        verbose_name = "ACS Variable"
        ordering = ["table_code", "variable_code"]
        indexes = [
            models.Index(fields=["table_code", "variable_code"]),
        ]

    def __str__(self):
        return f"{self.variable_code}: {self.concept or self.label[:60]}"
