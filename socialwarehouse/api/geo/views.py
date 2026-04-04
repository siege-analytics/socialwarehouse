"""Geospatial API views — DSTK replacement.

Provides geocoding, point-in-polygon, boundary retrieval, proximity,
and intersection endpoints. Wraps siege_utilities BoundaryManager
spatial queries.
"""

import json

from django.contrib.gis.geos import Point
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from socialwarehouse.api.pagination import GeoJSONPagination, StandardPagination
from socialwarehouse.api.throttling import BulkExportThrottle, GeocodeThrottle

from siege_utilities.geo.django.models.boundaries import (
    CongressionalDistrict,
    County,
    Place,
    State,
    Tract,
    ZCTA,
)
from siege_utilities.geo.django.models.political import (
    StateLegislativeLower,
    StateLegislativeUpper,
    VTD,
)
from siege_utilities.geo.django.models.timezone import TimezoneGeometry

# Map of boundary type slugs to model classes
BOUNDARY_MODELS = {
    "state": State,
    "county": County,
    "tract": Tract,
    "place": Place,
    "zcta": ZCTA,
    "cd": CongressionalDistrict,
    "state_leg_upper": StateLegislativeUpper,
    "state_leg_lower": StateLegislativeLower,
    "vtd": VTD,
    "timezone": TimezoneGeometry,
}

DEFAULT_GEOCODE_TYPES = [
    "state", "county", "cd", "state_leg_upper", "state_leg_lower", "tract", "timezone",
]


def _serialize_boundary(obj, include_geometry=False):
    """Serialize a boundary object to a dict."""
    data = {
        "geoid": getattr(obj, "geoid", getattr(obj, "feature_id", None)),
        "name": obj.name,
        "vintage_year": getattr(obj, "vintage_year", None),
    }
    if hasattr(obj, "abbreviation"):
        data["abbreviation"] = obj.abbreviation
    if hasattr(obj, "state_fips"):
        data["state_fips"] = obj.state_fips
    if hasattr(obj, "district_number"):
        data["district_number"] = obj.district_number
    if hasattr(obj, "congress_number"):
        data["congress_number"] = obj.congress_number
    if hasattr(obj, "timezone_id"):
        data["timezone_id"] = obj.timezone_id
    if hasattr(obj, "utc_offset_std"):
        data["utc_offset_std"] = obj.utc_offset_std
    if hasattr(obj, "area_land"):
        data["area_land"] = obj.area_land
    if hasattr(obj, "area_water"):
        data["area_water"] = obj.area_water
    if include_geometry and hasattr(obj, "geometry") and obj.geometry:
        data["geometry"] = json.loads(obj.geometry.geojson)
    return data


@api_view(["GET"])
@throttle_classes([GeocodeThrottle])
def geocode(request):
    """Point-in-polygon geocoding: coordinates or address → containing boundaries.

    Query parameters:
        lat/lon: Coordinates (WGS 84). Required if no address.
        address: Forward geocode via Nominatim. Required if no lat/lon.
        year: Vintage year for boundaries.
        date: Return boundaries valid on this date (YYYY-MM-DD).
        types: Comma-separated boundary types.
        include_geometry: Include GeoJSON geometry (default: false).
        include_demographics: Include demographic data (default: false).
    """
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    address = request.query_params.get("address")
    year = request.query_params.get("year")
    date_str = request.query_params.get("date")
    types_param = request.query_params.get("types")
    include_geometry = request.query_params.get("include_geometry", "false").lower() == "true"
    include_demographics = request.query_params.get("include_demographics", "false").lower() == "true"

    if address and not (lat and lon):
        coords = _forward_geocode(address)
        if coords is None:
            return Response(
                {"error": "Could not geocode address", "address": address},
                status=status.HTTP_404_NOT_FOUND,
            )
        lat, lon = coords
        geocoded_from = "address"
    elif lat and lon:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return Response({"error": "lat and lon must be numeric"}, status=status.HTTP_400_BAD_REQUEST)
        geocoded_from = "coordinates"
    else:
        return Response({"error": "Provide lat+lon or address parameter"}, status=status.HTTP_400_BAD_REQUEST)

    point = Point(lon, lat, srid=4326)

    requested_types = [t.strip() for t in types_param.split(",")] if types_param else DEFAULT_GEOCODE_TYPES
    year_int = int(year) if year else None

    boundaries = {}
    for btype in requested_types:
        model = BOUNDARY_MODELS.get(btype)
        if model is None:
            continue

        qs = model.objects.containing_point(point)

        if year_int:
            qs = qs.for_year(year_int) if hasattr(qs, "for_year") else qs.filter(vintage_year=year_int)
        elif date_str:
            from datetime import date as dt_date
            d = dt_date.fromisoformat(date_str)
            qs = qs.valid_on(d) if hasattr(qs, "valid_on") else qs

        obj = qs.first()
        if obj:
            boundaries[btype] = _serialize_boundary(obj, include_geometry=include_geometry)

    result = {
        "query": {"lat": lat, "lon": lon, "geocoded_from": geocoded_from},
        "boundaries": boundaries,
    }
    if address:
        result["query"]["address"] = address
    if include_demographics and boundaries:
        result["demographics"] = _get_demographics_for_boundaries(boundaries, year_int)

    return Response(result)


@api_view(["GET"])
@throttle_classes([GeocodeThrottle])
def reverse_geocode(request):
    """Reverse geocode: lat/lon → nearest address via Nominatim."""
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")

    if not lat or not lon:
        return Response({"error": "lat and lon parameters are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return Response({"error": "lat and lon must be numeric"}, status=status.HTTP_400_BAD_REQUEST)

    result = _reverse_geocode(lat, lon)
    if result is None:
        return Response(
            {"error": "No address found for coordinates", "lat": lat, "lon": lon},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({"query": {"lat": lat, "lon": lon}, "address": result})


@api_view(["GET"])
@throttle_classes([GeocodeThrottle])
def standardize_address(request):
    """Standardize an address string without geocoding."""
    address = request.query_params.get("address")
    if not address:
        return Response({"error": "address parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

    standardized = _standardize_address(address)
    return Response({"original": address, "standardized": standardized})


@api_view(["GET"])
def boundary_list(request, boundary_type):
    """List boundaries of a given type with filtering and pagination."""
    model = BOUNDARY_MODELS.get(boundary_type)
    if model is None:
        return Response(
            {"error": f"Unknown boundary type: {boundary_type}", "valid_types": list(BOUNDARY_MODELS.keys())},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = model.objects.all()

    year = request.query_params.get("year")
    if year:
        qs = qs.filter(vintage_year=int(year))

    state_fips = request.query_params.get("state_fips")
    if state_fips and hasattr(model, "state_fips"):
        qs = qs.filter(state_fips=state_fips)

    geoid = request.query_params.get("geoid")
    if geoid:
        qs = qs.filter(geoid=geoid)

    geoid_prefix = request.query_params.get("geoid__startswith")
    if geoid_prefix:
        qs = qs.filter(geoid__startswith=geoid_prefix)

    include_geometry = request.query_params.get("include_geometry", "false").lower() == "true"
    output_format = request.query_params.get("format", "json")

    if output_format == "geojson":
        paginator = GeoJSONPagination()
        page = paginator.paginate_queryset(qs, request)
        features = [
            {
                "type": "Feature",
                "geometry": json.loads(obj.geometry.geojson) if obj.geometry else None,
                "properties": _serialize_boundary(obj, include_geometry=False),
            }
            for obj in page
        ]
        return paginator.get_paginated_response({"type": "FeatureCollection", "features": features})

    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    data = [_serialize_boundary(obj, include_geometry=include_geometry) for obj in page]
    return paginator.get_paginated_response(data)


@api_view(["GET"])
@method_decorator(cache_page(60 * 60 * 24 * 7), name="dispatch")
def boundary_detail(request, boundary_type, geoid):
    """Retrieve a single boundary by type and GEOID. Always includes geometry."""
    model = BOUNDARY_MODELS.get(boundary_type)
    if model is None:
        return Response({"error": f"Unknown boundary type: {boundary_type}"}, status=status.HTTP_400_BAD_REQUEST)

    year = request.query_params.get("year")
    qs = model.objects.filter(geoid=geoid)
    if year:
        qs = qs.filter(vintage_year=int(year))
    else:
        qs = qs.order_by("-vintage_year")

    obj = qs.first()
    if obj is None:
        return Response(
            {"error": f"{boundary_type} with geoid={geoid} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(_serialize_boundary(obj, include_geometry=True))


@api_view(["GET"])
@throttle_classes([GeocodeThrottle])
def proximity(request):
    """Find boundaries within a distance of a point."""
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    btype = request.query_params.get("type")
    distance = request.query_params.get("distance")

    if not all([lat, lon, btype, distance]):
        return Response(
            {"error": "lat, lon, type, and distance parameters are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    model = BOUNDARY_MODELS.get(btype)
    if model is None:
        return Response(
            {"error": f"Unknown boundary type: {btype}", "valid_types": list(BOUNDARY_MODELS.keys())},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        point = Point(float(lon), float(lat), srid=4326)
        distance_m = float(distance)
    except (TypeError, ValueError):
        return Response({"error": "lat, lon, and distance must be numeric"}, status=status.HTTP_400_BAD_REQUEST)

    limit = int(request.query_params.get("limit", 20))
    year = request.query_params.get("year")

    qs = model.objects.nearest(point, max_distance_m=distance_m)
    if year:
        qs = qs.filter(vintage_year=int(year))

    results = []
    for obj in qs[:limit]:
        data = _serialize_boundary(obj)
        if hasattr(obj, "distance"):
            data["distance_m"] = obj.distance.m
        results.append(data)

    return Response({
        "query": {"lat": float(lat), "lon": float(lon), "type": btype, "distance": distance_m},
        "results": results,
        "count": len(results),
    })


@api_view(["GET"])
def intersections(request):
    """Query pre-computed boundary intersections."""
    source_type = request.query_params.get("source_type")
    source_id = request.query_params.get("source_id")
    target_type = request.query_params.get("target_type")
    year = request.query_params.get("year")

    if not all([source_type, source_id, target_type]):
        return Response(
            {"error": "source_type, source_id, and target_type are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from socialwarehouse.geo.models import (
        CountyCongressionalDistrictIntersection,
        VTDCongressionalDistrictIntersection,
    )

    typed_models = {
        ("county", "cd"): (CountyCongressionalDistrictIntersection, "siege_county__geoid"),
        ("vtd", "cd"): (VTDCongressionalDistrictIntersection, "siege_vtd__geoid"),
    }

    key = (source_type, target_type)
    model_info = typed_models.get(key)

    if model_info:
        model, source_filter = model_info
        qs = model.objects.filter(**{source_filter: source_id})
        if year:
            qs = qs.filter(year=int(year))

        results = []
        for obj in qs:
            data = {
                "pct_of_source": float(getattr(obj, f"pct_of_{source_type}", 0)),
                "pct_of_cd": float(obj.pct_of_cd) if hasattr(obj, "pct_of_cd") else None,
                "intersection_area_sqm": obj.intersection_area_sqm,
                "is_dominant": obj.is_dominant,
            }
            if hasattr(obj, "siege_cd"):
                data["target_id"] = obj.siege_cd.geoid if obj.siege_cd else None
            if hasattr(obj, "relationship"):
                data["relationship"] = obj.relationship
            results.append(data)
    else:
        results = []

    return Response({
        "query": {"source_type": source_type, "source_id": source_id, "target_type": target_type},
        "intersections": results,
        "count": len(results),
    })


# --- Internal helpers ---

def _forward_geocode(address):
    """Forward geocode via Nominatim. Returns (lat, lon) or None."""
    try:
        from siege_utilities.geo.geocoding import get_coordinates
        result = get_coordinates(address, country_codes=["us"])
        if result and result.latitude and result.longitude:
            return (result.latitude, result.longitude)
    except Exception:
        pass
    return None


def _reverse_geocode(lat, lon):
    """Reverse geocode via Nominatim. Returns address dict or None."""
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="socialwarehouse-api")
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True)
        if location:
            return {
                "display_name": location.address,
                "lat": location.latitude,
                "lon": location.longitude,
                "raw": location.raw.get("address", {}),
            }
    except Exception:
        pass
    return None


def _standardize_address(address):
    """Standardize an address string. Returns dict of parsed components."""
    parts = [p.strip() for p in address.split(",")]
    result = {"input": address, "components": {}}
    if len(parts) >= 3:
        result["components"]["street"] = parts[0]
        result["components"]["city"] = parts[1]
        state_zip = parts[2].strip().split()
        if state_zip:
            result["components"]["state"] = state_zip[0]
        if len(state_zip) > 1:
            result["components"]["zip"] = state_zip[1]
    elif len(parts) == 2:
        result["components"]["street"] = parts[0]
        result["components"]["city_state_zip"] = parts[1]
    else:
        result["components"]["raw"] = address
    return result


def _get_demographics_for_boundaries(boundaries, year=None):
    """Fetch demographics for geocoded boundaries."""
    from siege_utilities.geo.django.models.demographics import DemographicSnapshot
    from django.contrib.contenttypes.models import ContentType

    demographics = {}
    for btype, bdata in boundaries.items():
        geoid = bdata.get("geoid")
        if not geoid:
            continue

        model = BOUNDARY_MODELS.get(btype)
        if not model:
            continue

        ct = ContentType.objects.get_for_model(model)
        qs = DemographicSnapshot.objects.filter(content_type=ct, object_id=geoid)
        if year:
            qs = qs.filter(year=year)
        else:
            qs = qs.order_by("-year")

        snapshot = qs.first()
        if snapshot:
            demographics[btype] = {
                "year": snapshot.year,
                "total_population": snapshot.total_population,
                "median_household_income": snapshot.median_household_income,
                "median_age": snapshot.median_age,
            }

    return demographics
