"""
Address model — the central record in socialwarehouse.

Stores a US address with geocoding metadata, Census unit linkages (GEOIDs),
and optional ForeignKeys to siege_utilities boundary models for rich
hierarchical queries.

Design:
    GEOIDs are primary (string-indexed, fast lookups, year-flexible).
    ForeignKeys are optional (for ORM traversal: address.siege_vtd.county.state.name).
    Both approaches coexist — GEOIDs for bulk operations, FKs for Django admin and
    rich queries.
"""

from django.contrib.gis.db import models
from django.utils import timezone


class Address(models.Model):
    """
    A geocoded US address with Census boundary assignments.

    Fields are based on the SmartyStreets/USPS address component model,
    extended with geocoding metadata and Census unit linkages.
    """

    # ── Address components ───────────────────────────────────────────────
    primary_number = models.CharField(max_length=250, null=True, blank=True, default=None)
    street_name = models.CharField(max_length=250, null=True, blank=True, default=None)
    street_suffix = models.CharField(max_length=250, null=True, blank=True, default=None)
    city_name = models.CharField(max_length=250, null=True, blank=True, default=None)
    default_city_name = models.CharField(max_length=250, null=True, blank=True, default=None)
    state_abbreviation = models.CharField(max_length=2, null=True, blank=True, default=None)
    zip5 = models.CharField(max_length=5, null=True, blank=True, default=None)
    delivery_point = models.CharField(max_length=99, null=True, blank=True, default=None)
    delivery_point_check_digit = models.CharField(max_length=99, null=True, blank=True, default=None)

    # ── USPS & RDI classification ────────────────────────────────────────
    record_type = models.CharField(max_length=250, null=True, blank=True, default=None)
    zip_type = models.CharField(max_length=250, null=True, blank=True, default=None)
    county_fips = models.CharField(max_length=250, null=True, blank=True, default=None)
    county_name = models.CharField(max_length=250, null=True, blank=True, default=None)
    carrier_route = models.CharField(max_length=250, null=True, blank=True, default=None)
    congressional_district = models.CharField(max_length=250, null=True, blank=True, default=None)
    rdi = models.CharField(max_length=250, null=True, blank=True, default=None)
    elot_sequence = models.CharField(max_length=250, null=True, blank=True, default=None)
    elot_sort = models.CharField(max_length=250, null=True, blank=True, default=None)

    # ── Coordinates ──────────────────────────────────────────────────────
    latitude = models.DecimalField(max_digits=22, decimal_places=16, null=True, blank=True, default=None)
    longitude = models.DecimalField(max_digits=22, decimal_places=16, null=True, blank=True, default=None)
    coordinate_license = models.CharField(max_length=250, null=True, blank=True, default=None)
    precision = models.CharField(max_length=250, null=True, blank=True, default=None)
    time_zone = models.CharField(max_length=250, null=True, blank=True, default=None)
    utc_offset = models.CharField(max_length=250, null=True, blank=True, default=None)

    # ── GeoDjango geometry ───────────────────────────────────────────────
    geom = models.PointField(srid=4326, null=True, blank=True, default=None)

    # ── Geocoding metadata ───────────────────────────────────────────────
    geocoded = models.BooleanField(default=False, help_text="Whether address has been geocoded")
    geocode_quality = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="Quality: Rooftop, Interpolated, Approximate, Zip",
    )
    geocode_source = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="Source: Census, Google, Nominatim, SmartyStreets",
    )
    geocoded_at = models.DateTimeField(null=True, blank=True)

    # ── Census year context ──────────────────────────────────────────────
    census_year = models.IntegerField(
        default=2020,
        help_text="Census year for boundary assignment (2010, 2020)",
    )

    # ── Census unit GEOIDs (primary, string-indexed) ─────────────────────
    state_geoid = models.CharField(max_length=2, null=True, blank=True)
    county_geoid = models.CharField(max_length=5, null=True, blank=True)
    tract_geoid = models.CharField(max_length=11, null=True, blank=True)
    block_group_geoid = models.CharField(max_length=12, null=True, blank=True)
    block_geoid = models.CharField(max_length=15, null=True, blank=True)
    vtd_geoid = models.CharField(max_length=11, null=True, blank=True)
    cd_geoid = models.CharField(max_length=4, null=True, blank=True)
    sldl_geoid = models.CharField(
        max_length=5, null=True, blank=True,
        help_text="State Legislative District Lower GEOID (state FIPS + district)",
    )
    sldu_geoid = models.CharField(
        max_length=5, null=True, blank=True,
        help_text="State Legislative District Upper GEOID (state FIPS + district)",
    )
    census_units_assigned_at = models.DateTimeField(null=True, blank=True)

    # ── siege_geo ForeignKeys (canonical) ────────────────────────────────
    siege_state = models.ForeignKey(
        "siege_geo.State", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_county = models.ForeignKey(
        "siege_geo.County", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_tract = models.ForeignKey(
        "siege_geo.Tract", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_block_group = models.ForeignKey(
        "siege_geo.BlockGroup", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_cd = models.ForeignKey(
        "siege_geo.CongressionalDistrict", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_vtd = models.ForeignKey(
        "siege_geo.VTD", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_sldl = models.ForeignKey(
        "siege_geo.StateLegislativeLower", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )
    siege_sldu = models.ForeignKey(
        "siege_geo.StateLegislativeUpper", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sw_addresses", db_constraint=False,
    )

    class Meta:
        db_table = "sw_geo_address"
        indexes = [
            models.Index(fields=["state_abbreviation", "city_name"]),
            models.Index(fields=["county_fips"]),
            models.Index(fields=["congressional_district"]),
            models.Index(fields=["census_year"]),
            models.Index(fields=["geocoded"]),
            models.Index(fields=["state_geoid", "county_geoid"]),
            models.Index(fields=["cd_geoid", "census_year"]),
            models.Index(fields=["vtd_geoid", "census_year"]),
            models.Index(fields=["sldl_geoid", "census_year"]),
            models.Index(fields=["sldu_geoid", "census_year"]),
        ]

    def __str__(self):
        return f"{self.primary_number} {self.street_name} {self.street_suffix}"

    def assign_census_units_from_fips(self, state_fips, county_fips, tract, block):
        """
        Construct GEOIDs from Census API FIPS codes (no spatial join needed).

        Use when the Census Geocoder returns FIPS codes directly.
        """
        if state_fips:
            self.state_geoid = state_fips
        if state_fips and county_fips:
            self.county_geoid = f"{state_fips}{county_fips}"
        if state_fips and county_fips and tract:
            self.tract_geoid = f"{state_fips}{county_fips}{tract}"
            if block and len(block) >= 1:
                self.block_group_geoid = f"{state_fips}{county_fips}{tract}{block[0]}"
            else:
                self.block_group_geoid = f"{state_fips}{county_fips}{tract}"
        if state_fips and county_fips and tract and block:
            self.block_geoid = f"{state_fips}{county_fips}{tract}{block}"

    def populate_foreign_keys(self):
        """
        Populate siege_geo FK references from GEOIDs.

        Call after census unit assignment to enable rich hierarchical queries
        like address.siege_vtd.county.state.name.
        """
        from siege_utilities.geo.django.models import (
            State, County, Tract, BlockGroup,
            CongressionalDistrict, VTD,
            StateLegislativeLower, StateLegislativeUpper,
        )

        fk_map = [
            ("state_geoid", "siege_state", State),
            ("county_geoid", "siege_county", County),
            ("tract_geoid", "siege_tract", Tract),
            ("block_group_geoid", "siege_block_group", BlockGroup),
            ("cd_geoid", "siege_cd", CongressionalDistrict),
            ("vtd_geoid", "siege_vtd", VTD),
            ("sldl_geoid", "siege_sldl", StateLegislativeLower),
            ("sldu_geoid", "siege_sldu", StateLegislativeUpper),
        ]

        for geoid_field, fk_field, model_cls in fk_map:
            geoid = getattr(self, geoid_field)
            if geoid:
                obj = model_cls.objects.filter(
                    geoid=geoid, vintage_year=self.census_year
                ).first()
                setattr(self, fk_field, obj)

        self.save()
        return True


# Backwards-compatible alias
United_States_Address = Address
