"""Unit tests for the per-region projected-CRS lookup (M5 / SW#149) and the
SW#185 cross-region opt-in (EPSG:6933 for commensurable areas across regions).
"""

import pytest

from socialwarehouse.geo.projection import (
    EPSG_GLOBAL_EQUAL_AREA,
    area_srid_for_geoid,
    area_srid_for_state_fips,
    cross_region_srid,
)


@pytest.mark.parametrize(
    "state_fips,expected",
    [
        ("06", 5070),   # CA (CONUS)
        ("48", 5070),   # TX (CONUS)
        ("36", 5070),   # NY (CONUS)
        ("02", 3338),   # AK
        ("15", 3563),   # HI
        ("72", 32161),  # PR
        ("78", 32161),  # USVI
        ("60", EPSG_GLOBAL_EQUAL_AREA),  # American Samoa
        ("66", EPSG_GLOBAL_EQUAL_AREA),  # Guam
        ("69", EPSG_GLOBAL_EQUAL_AREA),  # Northern Mariana
    ],
)
def test_area_srid_for_state_fips_known_regions(state_fips, expected):
    assert area_srid_for_state_fips(state_fips) == expected


def test_area_srid_for_state_fips_empty_falls_back_to_global():
    assert area_srid_for_state_fips("") == EPSG_GLOBAL_EQUAL_AREA
    assert area_srid_for_state_fips(None) == EPSG_GLOBAL_EQUAL_AREA


def test_area_srid_for_geoid_uses_two_char_prefix():
    # County GEOID = state(2) + county(3)
    assert area_srid_for_geoid("06075") == 5070   # SF County, CA
    assert area_srid_for_geoid("02020") == 3338   # Anchorage, AK
    # VTD GEOID = state(2) + county(3) + vtd(6)
    assert area_srid_for_geoid("06075123456") == 5070
    assert area_srid_for_geoid("15003000123") == 3563  # Honolulu


def test_area_srid_for_geoid_empty_falls_back_to_global():
    assert area_srid_for_geoid("") == EPSG_GLOBAL_EQUAL_AREA
    assert area_srid_for_geoid(None) == EPSG_GLOBAL_EQUAL_AREA


# ---------------------------------------------------------------------------
# SW#185: cross-region opt-in
# ---------------------------------------------------------------------------


def test_cross_region_srid_constant():
    assert cross_region_srid() == EPSG_GLOBAL_EQUAL_AREA


@pytest.mark.parametrize(
    "state_fips",
    ["06", "48", "02", "15", "72"],
)
def test_cross_region_kwarg_overrides_region_srid(state_fips):
    """When cross_region=True, every input maps to 6933 — that's the
    whole point: commensurable areas across regions.
    """
    assert area_srid_for_state_fips(state_fips, cross_region=True) == EPSG_GLOBAL_EQUAL_AREA
    assert area_srid_for_geoid(state_fips + "075", cross_region=True) == EPSG_GLOBAL_EQUAL_AREA


def test_cross_region_false_is_default_behavior():
    assert area_srid_for_state_fips("06") == area_srid_for_state_fips("06", cross_region=False)
    assert area_srid_for_geoid("06075") == area_srid_for_geoid("06075", cross_region=False)
