"""Unit tests for the per-region projected-CRS lookup (M5 / SW#149)."""

import pytest

from socialwarehouse.geo.projection import (
    EPSG_GLOBAL_EQUAL_AREA,
    area_srid_for_geoid,
    area_srid_for_state_fips,
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
