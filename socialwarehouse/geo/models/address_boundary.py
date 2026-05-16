"""
Address Boundary Period Model

Records which geographic boundaries an address falls within for each Census
vintage AND redistricting plan. This enables temporal queries like:

    "What congressional district was this donor in on June 15, 2023?"

An address can have multiple boundary period records for the same Census
vintage when court-ordered redistricting changes political boundaries
mid-cycle. Static boundaries (county, tract) stay the same; political
boundaries (CD, SLDL, SLDU) differ by active plan.

Example:
    address=123 Main St, vintage=2020, plan=AL Enacted       → CD-07
    address=123 Main St, vintage=2020, plan=Milligan Interim  → CD-02
    address=123 Main St, vintage=2020, plan=Milligan Final    → CD-02
"""

from django.db import models


class AddressBoundaryPeriod(models.Model):
    """
    Snapshot of an address's boundary assignments for a specific Census vintage
    and redistricting plan.

    For static boundaries (state, county, tract, block group), the assignment
    is the same regardless of plan — these are decadal Census boundaries.

    For political boundaries (CD, SLDL, SLDU), the assignment depends on
    which redistricting plan was active. If redistricting_plan is NULL,
    the Census-drawn boundaries are used (the default).
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

    # Temporal context — which plan was active when this assignment was made
    redistricting_plan = models.ForeignKey(
        "siege_geo.RedistrictingPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="sw_boundary_periods",
        help_text="Active redistricting plan (NULL = Census default boundaries)",
    )
    congressional_term = models.ForeignKey(
        "siege_geo.CongressionalTerm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="sw_boundary_periods",
        help_text="Congressional term context for this assignment",
    )
    context_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="The date this assignment is valid for (resolves plan)",
    )

    # GEOIDs for each boundary level
    # Static boundaries (don't change with redistricting plans)
    state_geoid = models.CharField(max_length=2, null=True, blank=True)
    county_geoid = models.CharField(max_length=5, null=True, blank=True)
    tract_geoid = models.CharField(max_length=11, null=True, blank=True)
    block_group_geoid = models.CharField(max_length=12, null=True, blank=True)
    block_geoid = models.CharField(max_length=15, null=True, blank=True)
    vtd_geoid = models.CharField(max_length=11, null=True, blank=True)

    # Political boundaries (change with redistricting plans)
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

    # Plan-specific FKs (for districts that come from a redistricting plan, not Census)
    plan_district_cd = models.ForeignKey(
        "siege_geo.PlanDistrict", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False,
        related_name="sw_cd_assignments",
        help_text="PlanDistrict for CD if using a redistricting plan",
    )
    plan_district_sldl = models.ForeignKey(
        "siege_geo.PlanDistrict", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False,
        related_name="sw_sldl_assignments",
        help_text="PlanDistrict for SLDL if using a redistricting plan",
    )
    plan_district_sldu = models.ForeignKey(
        "siege_geo.PlanDistrict", on_delete=models.SET_NULL,
        null=True, blank=True, db_constraint=False,
        related_name="sw_sldu_assignments",
        help_text="PlanDistrict for SLDU if using a redistricting plan",
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
            ("PLAN_SPATIAL_JOIN", "PostGIS spatial join against redistricting plan"),
            ("MANUAL", "Manual assignment"),
        ],
        default="SPATIAL_JOIN",
    )

    class Meta:
        db_table = "sw_geo_address_boundary_period"
        # nulls_distinct=False: NULL redistricting_plan means "Census default",
        # which should be unique per (address, vintage) -- not a distinct row
        # per NULL as PG's default semantics would have it. Requires PG 15+.
        constraints = [
            models.UniqueConstraint(
                fields=["address", "vintage", "redistricting_plan"],
                name="uniq_addr_vintage_plan_nulls_eq",
                nulls_distinct=False,
            ),
        ]
        ordering = ["address", "-vintage", "-context_date"]
        verbose_name = "Address Boundary Period"
        verbose_name_plural = "Address Boundary Periods"
        indexes = [
            models.Index(fields=["vintage", "cd_geoid"]),
            models.Index(fields=["vintage", "state_geoid", "county_geoid"]),
            models.Index(fields=["vintage", "vtd_geoid"]),
            models.Index(fields=["vintage", "sldl_geoid"]),
            models.Index(fields=["vintage", "sldu_geoid"]),
            models.Index(fields=["context_date", "state_geoid"]),
            models.Index(fields=["redistricting_plan", "cd_geoid"]),
        ]

    def __str__(self):
        plan = f" [{self.redistricting_plan}]" if self.redistricting_plan else ""
        return f"Address {self.address_id} @ {self.vintage.decade} Census{plan}"
