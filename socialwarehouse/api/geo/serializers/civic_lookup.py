"""Serializers for the civic_lookup endpoint (SW#272).

Designed for the address -> district memberships composition described
in `docs/api/civic-lookup.md`. Uses DRF + DRF-GIS so the optional
GeoJSON Point comes through `rest_framework_gis.fields.GeometryField`
rather than hand-rolled lat/lon dicts.
"""

from __future__ import annotations

from rest_framework import serializers
from rest_framework_gis.fields import GeometryField

from socialwarehouse.geo.models import Address
from socialwarehouse.warehouse.models import DimPerson


_ADDRESS_SUMMARY_FIELDS = (
    "id",
    "primary_number",
    "street_name",
    "street_suffix",
    "city_name",
    "state_abbreviation",
    "zip5",
    "zip4",
    "latitude",
    "longitude",
    "geocoded",
    "geocode_source",
    "census_year",
)


class AddressSummarySerializer(serializers.ModelSerializer):
    """Non-geo Address fields for the civic_lookup response.

    Use when `include_geometry=false` (the default). Lighter payload
    than the geometry-bearing variant.
    """

    class Meta:
        model = Address
        fields = _ADDRESS_SUMMARY_FIELDS


class AddressWithGeometrySerializer(serializers.ModelSerializer):
    """Address summary plus GeoJSON Point.

    The `geom` field uses DRF-GIS's GeometryField which emits proper
    GeoJSON (`{"type": "Point", "coordinates": [lon, lat]}`) instead of
    the Django-internal WKT or hand-rolled lat/lon shape. When
    `address.geom` is null on the model (un-geocoded address),
    `geom` serializes as null.
    """

    geom = GeometryField(allow_null=True, required=False)

    class Meta:
        model = Address
        fields = _ADDRESS_SUMMARY_FIELDS + ("geom",)


class PersonSummarySerializer(serializers.ModelSerializer):
    """Minimal DimPerson fields surfaced when `include_people=true`.

    PII-friendly default: identity is keyed only by vendor + vendor_voter_id +
    registration_state. Name, DOB, contact, scoring, vote history are NOT
    surfaced here; consumers who need them can query the warehouse directly.
    """

    class Meta:
        model = DimPerson
        fields = ("vendor", "vendor_voter_id", "registration_state")
