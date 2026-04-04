"""
Address Boundary Period Model

Records which geographic boundaries an address falls within for each Census
vintage. This enables temporal queries like:

    "What congressional district was this donor in during the 2016 cycle?"

One AddressBoundaryPeriod row per address per census vintage.
"""

from django.db import models


class AddressBoundaryPeriod(models.Model):
    """
    Snapshot of an address's boundary assignments for a specific Census vintage.

    Links an address to its containing boundaries (state, county, tract, CD,
    VTD, SLDL, SLDU) for a given Census decade. When boundaries change due
    to redistricting, a new row is created for the new vintage.

    Example:
        address=123 Main St, vintage=2010 → CD-07, County-031, ...
        address=123 Main St, vintage=2020 → CD-04, County-031, ...
    """

    address = models.ForeignKey(
        "sw_geo.Address",
        on_delete=models.CASCADE,
        related_name="boundary_periods",
    )
    vintage = models.ForeignKey(
        "sw_geo.CensusVintageConfig",
        on_delete=models.CASCADE,
        related_name="boundary_assignments",
    )

    # GEOIDs for each boundary level
    state_geoid = models.CharField(max_length=2, null=True, blank=True)
    county_geoid = models.CharField(max_length=5, null=True, blank=True)
    tract_geoid = models.CharField(max_length=11, null=True, blank=True)
    block_group_geoid = models.CharField(max_length=12, null=True, blank=True)
    block_geoid = models.CharField(max_length=15, null=True, blank=True)
    vtd_geoid = models.CharField(max_length=11, null=True, blank=True)
    cd_geoid = models.CharField(max_length=4, null=True, blank=True)
    sldl_geoid = models.CharField(max_length=5, null=True, blank=True)
    sldu_geoid = models.CharField(max_length=5, null=True, blank=True)

    # siege_geo ForeignKeys (optional, for rich queries)
    siege_state = models.ForeignKey(
        "siege_geo.State", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )
    siege_county = models.ForeignKey(
        "siege_geo.County", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )
    siege_tract = models.ForeignKey(
        "siege_geo.Tract", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )
    siege_cd = models.ForeignKey(
        "siege_geo.CongressionalDistrict", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )
    siege_vtd = models.ForeignKey(
        "siege_geo.VTD", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )
    siege_sldl = models.ForeignKey(
        "siege_geo.StateLegislativeLower", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )
    siege_sldu = models.ForeignKey(
        "siege_geo.StateLegislativeUpper", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False, related_name="sw_boundary_periods",
    )

    # Metadata
    assigned_at = models.DateTimeField(auto_now_add=True)
    assignment_method = models.CharField(
        max_length=30,
        choices=[
            ("SPATIAL_JOIN", "PostGIS spatial join"),
            ("CENSUS_API", "Census Geocoder API"),
            ("NOMINATIM", "Nominatim + spatial join"),
            ("FIPS_LOOKUP", "Direct FIPS code lookup"),
            ("MANUAL", "Manual assignment"),
        ],
        default="SPATIAL_JOIN",
    )

    class Meta:
        db_table = "sw_geo_address_boundary_period"
        unique_together = [["address", "vintage"]]
        ordering = ["address", "-vintage"]
        verbose_name = "Address Boundary Period"
        verbose_name_plural = "Address Boundary Periods"
        indexes = [
            models.Index(fields=["vintage", "cd_geoid"]),
            models.Index(fields=["vintage", "state_geoid", "county_geoid"]),
            models.Index(fields=["vintage", "vtd_geoid"]),
            models.Index(fields=["vintage", "sldl_geoid"]),
            models.Index(fields=["vintage", "sldu_geoid"]),
        ]

    def __str__(self):
        return f"Address {self.address_id} @ {self.vintage.decade} Census"
