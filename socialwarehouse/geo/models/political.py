"""
Political extension models for siege_geo boundaries.

OneToOne models storing political context (governor, representative, party,
legislature seats) that don't belong in siege_utilities' shared boundary
models. They link to siege_geo models via OneToOneField, keeping political
context separate from geometry.
"""

from django.db import models


class PoliticalState(models.Model):
    """Political context for a US state."""

    siege_state = models.OneToOneField(
        "siege_geo.State",
        on_delete=models.CASCADE,
        related_name="sw_political",
    )
    governor = models.CharField(max_length=255, blank=True, default="")
    governor_party = models.CharField(max_length=50, blank=True, default="")
    legislature_upper_seats = models.PositiveSmallIntegerField(default=0)
    legislature_lower_seats = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "sw_political_state"

    def __str__(self):
        return f"Political context for {self.siege_state}"


class PoliticalCongressionalDistrict(models.Model):
    """Political context for a congressional district."""

    siege_cd = models.OneToOneField(
        "siege_geo.CongressionalDistrict",
        on_delete=models.CASCADE,
        related_name="sw_political",
    )
    representative = models.CharField(max_length=255, blank=True, default="")
    party = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "sw_political_cd"

    def __str__(self):
        return f"Political context for {self.siege_cd}"


class PoliticalStateLegislativeUpper(models.Model):
    """Political context for a state senate district."""

    siege_sldu = models.OneToOneField(
        "siege_geo.StateLegislativeUpper",
        on_delete=models.CASCADE,
        related_name="sw_political",
    )
    current_senator = models.CharField(max_length=255, blank=True, default="")
    party = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "sw_political_sldu"

    def __str__(self):
        return f"Political context for {self.siege_sldu}"


class PoliticalStateLegislativeLower(models.Model):
    """Political context for a state house district."""

    siege_sldl = models.OneToOneField(
        "siege_geo.StateLegislativeLower",
        on_delete=models.CASCADE,
        related_name="sw_political",
    )
    current_representative = models.CharField(max_length=255, blank=True, default="")
    party = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "sw_political_sldl"

    def __str__(self):
        return f"Political context for {self.siege_sldl}"
