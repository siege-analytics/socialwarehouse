"""
Projected-CRS lookup for area math.

Picks an equal-area projected SRID for a given U.S. geography based on the
two-digit state FIPS prefix of its GEOID. Used by geometry-area code paths
that must measure in square meters rather than degree-squared.

End state: a single global equal-area projection (EPSG:6933, NSIDC EASE-Grid
2.0) replaces this per-region table. Tracked as a follow-up; see the design
note at docs/designs/m5-postgis-st-intersection.md.
"""

EPSG_GLOBAL_EQUAL_AREA = 6933

_REGIONAL_AREA_SRID = {
    "02": 3338,
    "15": 3563,
    "60": EPSG_GLOBAL_EQUAL_AREA,
    "66": EPSG_GLOBAL_EQUAL_AREA,
    "69": EPSG_GLOBAL_EQUAL_AREA,
    "72": 32161,
    "78": 32161,
}

_CONUS_AREA_SRID = 5070


def area_srid_for_state_fips(state_fips):
    """Return the projected SRID to use for area math given a state FIPS.

    Falls back to EPSG:6933 (global equal-area) when the input is missing or
    unrecognized — safer than refusing to compute, and the fallback CRS still
    produces a meaningful planar area.
    """
    if not state_fips:
        return EPSG_GLOBAL_EQUAL_AREA
    return _REGIONAL_AREA_SRID.get(str(state_fips)[:2], _CONUS_AREA_SRID)


def area_srid_for_geoid(geoid):
    """Convenience: state FIPS is always the leading 2 chars of a Census GEOID."""
    if not geoid:
        return EPSG_GLOBAL_EQUAL_AREA
    return area_srid_for_state_fips(str(geoid)[:2])
