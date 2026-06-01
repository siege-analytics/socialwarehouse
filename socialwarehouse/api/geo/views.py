"""Geospatial API views — DSTK replacement.

Provides geocoding, point-in-polygon, boundary retrieval, proximity,
and intersection endpoints. Uses queryset manager methods
(`containing_point`, `nearest`, standard Django ORM filters) on
siege_utilities boundary models. No `BoundaryManager` wrapper class is
imported or used; the previous wording of this docstring was stale.
(A4 / SW#115)
"""

import json
import logging

from django.contrib.gis.geos import Point
from django.views.decorators.cache import cache_page
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

logger = logging.getLogger("socialwarehouse.api.geo")

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
    """Serialize a boundary object to a dict.

    The `hasattr` chain below is intentional: BOUNDARY_MODELS span
    Census/political/timezone tables with genuinely different field
    sets, and a single endpoint serializes whichever model the caller
    requested. Per-field heterogeneity (A8 / SW#119):

    - `abbreviation`: State only
    - `state_fips`: County, Tract, Place, ZCTA, CongressionalDistrict,
      StateLegislativeUpper/Lower, VTD (any sub-state Census model)
    - `district_number`, `congress_number`: CongressionalDistrict only
    - `timezone_id`, `utc_offset_std`: TimezoneGeometry only
    - `area_land`, `area_water`: most Census boundaries; not on
      TimezoneGeometry or political models that don't carry TIGER metadata

    Replacing the chain with a per-model field map would be more code
    than the chain itself for the same behavior, so we keep the chain
    and document the diversity here. Mirrors the W6 (#110) pattern in
    `dimension_loader.py`.
    """
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


def _resolve_boundary_model(boundary_type):
    """Look up a model from BOUNDARY_MODELS or return a 400 Response.

    Single-type lookup helper used by boundary_list, boundary_detail, and
    proximity. Loop sites (geocode, _get_demographics_for_boundaries) iterate
    requested types and silently skip unknowns — they do not use this helper.

    Returns:
        (model, None) on a known boundary_type.
        (None, Response) with a 400 status and a valid_types list on miss.
    """
    model = BOUNDARY_MODELS.get(boundary_type)
    if model is None:
        return None, Response(
            {
                "error": f"Unknown boundary type: {boundary_type}",
                "valid_types": list(BOUNDARY_MODELS.keys()),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return model, None


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
    """Standardize an address string without geocoding.

    Best-effort placeholder: backed by `_standardize_address`, a naive
    comma-split US-only parser. Not suitable for international formats
    or addresses without commas. (A7 / SW#118)
    """
    address = request.query_params.get("address")
    if not address:
        return Response({"error": "address parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

    standardized = _standardize_address(address)
    return Response({"original": address, "standardized": standardized})


@api_view(["GET"])
def boundary_list(request, boundary_type):
    """List boundaries of a given type with filtering and pagination."""
    model, err = _resolve_boundary_model(boundary_type)
    if err is not None:
        return err

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


# 1-day TTL (was 7 days, A5 / SW#116). Boundary updates from upstream
# loaders (TIGER, RDH, etc.) ship on the order of weeks-to-months, so a
# 24h staleness window matches the actual update cadence and keeps
# operator surprise low after a re-load. Lacking a save-signal-driven
# invalidation, 1 day is the right blunt instrument.
@api_view(["GET"])
@cache_page(60 * 60 * 24)
def boundary_detail(request, boundary_type, geoid):
    """Retrieve a single boundary by type and GEOID. Always includes geometry."""
    model, err = _resolve_boundary_model(boundary_type)
    if err is not None:
        return err

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

    model, err = _resolve_boundary_model(btype)
    if err is not None:
        return err

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
    """Forward geocode via Nominatim. Returns (lat, lon) or None.

    Returns None on miss OR on failure; failures are logged at WARNING so
    operators can distinguish "no result" from "geocoder down / network /
    malformed query." Per writing-code:7 (no silent error swallowing).
    """
    try:
        from siege_utilities.geo.geocoding import get_coordinates
        result = get_coordinates(address, country_codes=["us"])
        if result and result.latitude and result.longitude:
            return (result.latitude, result.longitude)
        return None
    except Exception as e:
        logger.warning(
            "_forward_geocode failed for address=%r: %s: %s",
            address, type(e).__name__, e,
        )
        return None


def _reverse_geocode(lat, lon):
    """Reverse geocode via Nominatim. Returns address dict or None.

    Returns None on miss OR on failure; failures are logged at WARNING.
    Per writing-code:7 (no silent error swallowing).
    """
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
        return None
    except Exception as e:
        logger.warning(
            "_reverse_geocode failed for lat=%s lon=%s: %s: %s",
            lat, lon, type(e).__name__, e,
        )
        return None


def _standardize_address(address):
    """Standardize an address string. Returns dict of parsed components.

    PLACEHOLDER (A7 / SW#118): this is a naive comma-split that assumes
    a US-style "street, city, state zip" shape. It will misparse
    international formats, multi-line addresses, and anything without
    commas. Replace with `usaddress` (US-only) or `libpostal` (heavier,
    international) when the endpoint moves past placeholder status. The
    `standardize_address` view that calls this is explicitly documented
    as best-effort.

    The returned dict's outer `input` key was previously dead — the
    only caller (`standardize_address` at line 211) already surfaces
    the original address as the response's `original` key and ignores
    the inner `input`. Dropping it here. (A10 / SW#121)
    """
    parts = [p.strip() for p in address.split(",")]
    result = {"components": {}}
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


# ── Civic lookup (SW#272) ────────────────────────────────────────────
# Address -> district memberships. Composes the F11 boundary-cache
# fields on geo.Address into a single response. See
# `docs/api/civic-lookup.md` for the full contract.

from rest_framework.views import APIView

from socialwarehouse.api.geo.serializers import (
    AddressSummarySerializer,
    AddressWithGeometrySerializer,
    PersonSummarySerializer,
)
from socialwarehouse.geo.models import Address
from socialwarehouse.warehouse.models import (
    DimGeography,
    DimPerson,
    DimRedistrictingCycle,
)


# Address boundary-cache field name -> response district key + DimGeography
# summary_level. Cache field null -> district key omitted from response.
# (model_field, response_key, dim_geography_summary_level, boundary_url_slug)
_DISTRICT_FIELDS = (
    ("state_geoid", "state", "state", "state"),
    ("county_geoid", "county", "county", "county"),
    ("tract_geoid", "tract", "tract", "tract"),
    ("block_group_geoid", "block_group", "blockgroup", None),
    ("block_geoid", "block", "block", None),
    ("vtd_geoid", "vtd", "vtd", "vtd"),
    ("cd_geoid", "congressional", "cd", "cd"),
    ("sldu_geoid", "state_senate", "sldu", "state_leg_upper"),
    ("sldl_geoid", "state_house", "sldl", "state_leg_lower"),
    ("zcta_geoid", "zcta", "zcta", "zcta"),
)

_TRUTHY = {"1", "true", "yes", "y", "t"}


def _parse_bool(val):
    """Tolerant bool parser; default False on missing/unknown."""
    if val is None:
        return False
    return str(val).strip().lower() in _TRUTHY


def _lookup_canonical_address(address_str, state=None):
    """Return list of Address rows matching the input string.

    v1 is a literal-match path: parses the address into best-guess parts
    (primary_number + street_name + city_name + zcta_geoid as USPS-ZIP proxy) and queries.
    Returns 0, 1, or N rows; caller decides 404 / 200 / 409.

    Live geocoding for a fresh-address fallback is a follow-on; that
    path goes through the existing /api/geo/geocode/ endpoint first.
    """
    parts = [p.strip() for p in address_str.split(",")]
    qs = Address.objects.all()
    if state:
        qs = qs.filter(state_abbreviation__iexact=state)

    # Naive split: "123 Main St, Austin, TX 78701" -> primary_number, street,
    # city, state+zip. Operators with structured input should supply the
    # full canonical form; v1 doesn't try to be clever about parsing.
    if not parts:
        return list(qs[:5])

    # First chunk: house number + street.
    head_tokens = parts[0].split()
    if head_tokens:
        first = head_tokens[0]
        if first.isdigit():
            qs = qs.filter(primary_number=first)
            street_parts = head_tokens[1:]
        else:
            street_parts = head_tokens
        if street_parts:
            street_query = " ".join(street_parts)
            qs = qs.filter(street_name__iexact=street_query) | qs.filter(
                street_name__istartswith=street_parts[0]
            )

    # Second chunk: city (if present).
    if len(parts) > 1 and parts[1]:
        qs = qs.filter(city_name__iexact=parts[1])

    # Third chunk: state + zip (zip is what disambiguates).
    if len(parts) > 2 and parts[2]:
        for token in parts[2].split():
            if token.isdigit() and len(token) >= 5:
                # Address has no canonical zip field; zcta_geoid is the USPS-ZIP-like
                # proxy (Census ZIP Code Tabulation Area). Note ZCTA != ZIP exactly
                # but aligns for the bulk of residential addresses.
                qs = qs.filter(zcta_geoid=token[:5])

    return list(qs.order_by("id")[:10])


def _resolve_districts(address):
    """Read non-null boundary-cache fields off Address and look up names.

    DimGeography lookup is best-effort: queries by (geoid,
    vintage_year=address.census_year). Name null when no matching row.
    Null cache fields are OMITTED from the dict (not emitted as null)
    so absence is visible.

    Each district entry includes a HATEOAS ``url`` pointing to the
    boundary detail endpoint when the boundary type has a registered
    route; ``None`` otherwise (block_group, block have no detail
    endpoint in the current URL surface).
    """
    from django.urls import reverse

    out = {}
    vintage = address.census_year or None

    geoids_to_lookup = {}
    for field_name, response_key, summary_level, url_slug in _DISTRICT_FIELDS:
        geoid = getattr(address, field_name, None) or None
        if geoid:
            url = None
            if url_slug:
                try:
                    url = reverse(
                        "geo:boundary_detail",
                        kwargs={"boundary_type": url_slug, "geoid": geoid},
                    )
                except Exception:
                    pass
            out[response_key] = {"geoid": geoid, "name": None, "url": url}
            geoids_to_lookup[response_key] = (geoid, summary_level)

    if not geoids_to_lookup:
        return out

    geoid_list = [g for g, _ in geoids_to_lookup.values()]
    dim_filter = {"geoid__in": geoid_list}
    if vintage:
        dim_filter["vintage_year"] = vintage
    dim_rows = DimGeography.objects.filter(**dim_filter).values(
        "geoid", "summary_level", "name"
    )
    name_lookup = {(r["geoid"], r["summary_level"]): r["name"] for r in dim_rows}

    for response_key, (geoid, summary_level) in geoids_to_lookup.items():
        name = name_lookup.get((geoid, summary_level))
        if name:
            out[response_key]["name"] = name

    return out


def _resolve_redistricting_cycle(address):
    """Return {cycle_year, first_election_year} or None."""
    if not address.census_year:
        return None
    cycle = (
        DimRedistrictingCycle.objects.filter(census_year=address.census_year)
        .order_by("cycle_year")
        .first()
    )
    if cycle is None:
        return None
    return {
        "cycle_year": cycle.cycle_year,
        "first_election_year": cycle.first_election_year,
    }


def _resolve_people(address):
    """Return {count, items} for DimPerson rows at the address."""
    qs = DimPerson.objects.filter(address=address).order_by("vendor", "vendor_voter_id")
    items = PersonSummarySerializer(qs, many=True).data
    return {"count": len(items), "items": items}


def _not_found_payload(state=None):
    """Compose the 404 response with the geocode-endpoint hint."""
    if state:
        error = f"no matching Address row found in state {state}"
        hint = (
            "POST or GET /api/geo/geocode/?address=<...> to resolve a new "
            "address before calling civic_lookup, or omit ?state= to "
            "broaden the search"
        )
    else:
        error = "no matching Address row found"
        hint = (
            "POST or GET /api/geo/geocode/?address=<...> to resolve a new "
            "address before calling civic_lookup"
        )
    return {"error": error, "code": "address_not_found", "hint": hint}


class CivicLookupView(APIView):
    """Address -> district memberships endpoint.

    GET /api/geo/civic_lookup/?address=<str>[&state=<usps>][&include_people=true|false][&include_geometry=true|false]

    See `docs/api/civic-lookup.md` for the full contract.
    """

    throttle_classes = [GeocodeThrottle]

    def get(self, request):
        address_str = request.query_params.get("address", "").strip()
        if not address_str:
            return Response(
                {
                    "error": "address query parameter is required",
                    "code": "missing_address",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        state_raw = request.query_params.get("state", "").strip().upper()
        state = state_raw or None
        include_people = _parse_bool(request.query_params.get("include_people"))
        include_geometry = _parse_bool(request.query_params.get("include_geometry"))

        candidates = _lookup_canonical_address(address_str, state=state)
        if not candidates:
            return Response(
                _not_found_payload(state), status=status.HTTP_404_NOT_FOUND
            )
        if len(candidates) > 1:
            return Response(
                {
                    "error": "multiple Address rows match; refine the query",
                    "code": "ambiguous_address",
                    "candidate_count": len(candidates),
                    "hint": "supply ?state=<USPS> or include a more specific address line",
                },
                status=status.HTTP_409_CONFLICT,
            )

        address = candidates[0]
        if include_geometry:
            address_data = AddressWithGeometrySerializer(address).data
        else:
            address_data = AddressSummarySerializer(address).data

        payload = {
            "address": address_data,
            "districts": _resolve_districts(address),
        }
        cycle = _resolve_redistricting_cycle(address)
        if cycle is not None:
            payload["redistricting_cycle"] = cycle
        if include_people:
            payload["people"] = _resolve_people(address)

        return Response(payload, status=status.HTTP_200_OK)
