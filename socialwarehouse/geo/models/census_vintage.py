"""
Census Vintage Configuration

Maps Census decades to their effective year ranges for boundary assignment.
When geocoding an address from a 2018 filing, we need to know which Census
boundaries to use (2010 vintage). For a 2022 filing, use 2020 vintage.
"""

from django.db import models


class CensusVintageConfig(models.Model):
    """
    Configuration for which Census boundary vintage applies to which years.

    Example rows:
        decade=2010, effective_start=2010, effective_end=2019
        decade=2020, effective_start=2020, effective_end=2029

    Usage:
        vintage = CensusVintageConfig.for_year(2018)  # returns decade=2010
    """

    decade = models.IntegerField(
        primary_key=True,
        help_text="Census decade (1990, 2000, 2010, 2020)",
    )
    effective_start = models.IntegerField(
        help_text="First year this vintage's boundaries are used (inclusive)",
    )
    effective_end = models.IntegerField(
        help_text="Last year this vintage's boundaries are used (inclusive)",
    )
    description = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this vintage has boundaries loaded in the database",
    )

    class Meta:
        db_table = "sw_geo_census_vintage_config"
        ordering = ["decade"]
        verbose_name = "Census Vintage Configuration"
        verbose_name_plural = "Census Vintage Configurations"

    def __str__(self):
        return f"{self.decade} Census ({self.effective_start}-{self.effective_end})"

    @classmethod
    def for_year(cls, year):
        """Return the CensusVintageConfig whose effective range contains the given year."""
        return cls.objects.filter(
            effective_start__lte=year,
            effective_end__gte=year,
            is_active=True,
        ).first()

    @classmethod
    def seed_defaults(cls):
        """Seed the four standard Census decades."""
        defaults = [
            (1990, 1990, 1999, "1990 Census boundaries"),
            (2000, 2000, 2009, "2000 Census boundaries"),
            (2010, 2010, 2019, "2010 Census boundaries"),
            (2020, 2020, 2029, "2020 Census boundaries"),
        ]
        created = 0
        for decade, start, end, desc in defaults:
            _, was_created = cls.objects.get_or_create(
                decade=decade,
                defaults={
                    "effective_start": start,
                    "effective_end": end,
                    "description": desc,
                    "is_active": decade >= 2010,
                },
            )
            if was_created:
                created += 1
        return created
