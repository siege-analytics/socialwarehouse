"""
Projected-CRS lookup for area math.

SW#185 resolution: keep the per-region table as the **default** because the
regional CRSs (5070 CONUS, 3338 AK, 3563 HI, 32161 PR/USVI) are markedly
more accurate for in-region area math than 6933. For **cross-region**
comparisons — say, comparing a CD in HI against a CD in AL — callers
pass ``cross_region=True`` (or call :func:`cross_region_srid`) to get the
global equal-area CRS so the two areas are commensurable.

Default: per-region (precision within a region).
Opt-in: EPSG:6933 (NSIDC EASE-Grid 2.0) for cross-region comparisons.
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


def cross_region_srid():
    """Return the SRID to use when comparing areas across regions.

    EPSG:6933 (NSIDC EASE-Grid 2.0) is globally valid and equal-area, so
    a CONUS county's area is directly comparable to an HI / AK / PR county's
    area when both are measured in 6933. Pay ~3-5% area distortion vs the
    region-native SRID; in exchange, gain commensurability.
    """
    return EPSG_GLOBAL_EQUAL_AREA


def area_srid_for_state_fips(state_fips, *, cross_region=False):
    """Return the projected SRID for area math given a state FIPS.

    Default: per-region SRID (preferable for in-region precision).
    ``cross_region=True``: EPSG:6933 (globally valid; use when comparing
    across regions). Falls back to EPSG:6933 when the input is missing or
    unrecognized — safer than refusing to compute.
    """
    if cross_region:
        return EPSG_GLOBAL_EQUAL_AREA
    if not state_fips:
        return EPSG_GLOBAL_EQUAL_AREA
    return _REGIONAL_AREA_SRID.get(str(state_fips)[:2], _CONUS_AREA_SRID)


def area_srid_for_geoid(geoid, *, cross_region=False):
    """Convenience: state FIPS is always the leading 2 chars of a Census GEOID."""
    if cross_region:
        return EPSG_GLOBAL_EQUAL_AREA
    if not geoid:
        return EPSG_GLOBAL_EQUAL_AREA
    return area_srid_for_state_fips(str(geoid)[:2])
