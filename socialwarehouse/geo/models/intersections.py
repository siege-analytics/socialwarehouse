"""
Geographic Intersection Models

Pre-computed spatial relationships between geographic units.
Stores intersection geometries and overlap percentages for fast queries
without runtime spatial joins.

Clean break: siege_geo FKs only (no legacy TIGER FKs).
"""

from django.contrib.gis.db import models


class CountyCongressionalDistrictIntersection(models.Model):
    """
    Pre-computed County-CD intersections.

    Example: San Francisco County (06075) is split between:
        - CA-11: 42.3% of county
        - CA-12: 57.7% of county
    """

    siege_county = models.ForeignKey(
        "siege_geo.County",
        on_delete=models.CASCADE,
        related_name="sw_cd_intersections",
    )
    siege_cd = models.ForeignKey(
        "siege_geo.CongressionalDistrict",
        on_delete=models.CASCADE,
        related_name="sw_county_intersections",
    )
    year = models.IntegerField(help_text="Census year (both county and CD must match)")

    intersection_geom = models.MultiPolygonField(srid=4269)
    intersection_area_sqm = models.BigIntegerField()

    pct_of_county = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="% of County area that overlaps with CD",
    )
    pct_of_cd = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="% of CD area that overlaps with County",
    )

    relationship = models.CharField(
        max_length=20,
        choices=[
            ("COUNTY_IN_CD", "County fully within CD"),
            ("CD_IN_COUNTY", "CD fully within county"),
            ("SPLIT", "County split between CDs"),
        ],
    )
    is_dominant = models.BooleanField(
        default=False,
        help_text="True if this CD contains >50% of county",
    )
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_geo_intersection_county_cd"
        verbose_name = "County-CD Intersection"
        verbose_name_plural = "County-CD Intersections"
        unique_together = [["siege_county", "siege_cd", "year"]]
        indexes = [
            models.Index(fields=["year", "siege_county"]),
            models.Index(fields=["year", "siege_cd"]),
            models.Index(fields=["relationship"]),
            models.Index(fields=["is_dominant"]),
        ]
        ordering = ["siege_county", "-pct_of_county"]

    def __str__(self):
        return f"County {self.siege_county_id} ∩ CD {self.siege_cd_id} ({self.pct_of_county:.1f}%)"


class VTDCongressionalDistrictIntersection(models.Model):
    """
    Pre-computed VTD-CD intersections.

    Critical for donor attribution in split precincts.
    """

    siege_vtd = models.ForeignKey(
        "siege_geo.VTD",
        on_delete=models.CASCADE,
        related_name="sw_cd_intersections",
    )
    siege_cd = models.ForeignKey(
        "siege_geo.CongressionalDistrict",
        on_delete=models.CASCADE,
        related_name="sw_vtd_intersections",
    )
    year = models.IntegerField()

    intersection_geom = models.MultiPolygonField(srid=4269)
    intersection_area_sqm = models.BigIntegerField()

    pct_of_vtd = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="% of VTD in this CD (for proportional attribution)",
    )
    pct_of_cd = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="% of CD covered by this VTD",
    )
    is_dominant = models.BooleanField(
        default=False, db_index=True,
        help_text="True if >50% of VTD is in this CD",
    )
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_geo_intersection_vtd_cd"
        verbose_name = "VTD-CD Intersection"
        verbose_name_plural = "VTD-CD Intersections"
        unique_together = [["siege_vtd", "siege_cd", "year"]]
        indexes = [
            models.Index(fields=["year", "siege_vtd", "is_dominant"]),
            models.Index(fields=["year", "siege_cd"]),
        ]
        ordering = ["siege_vtd", "-pct_of_vtd"]

    def __str__(self):
        return f"VTD {self.siege_vtd_id} ∩ CD {self.siege_cd_id} ({self.pct_of_vtd:.1f}%)"
