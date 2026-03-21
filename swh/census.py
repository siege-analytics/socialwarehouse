"""
Census data download and loading via siege_utilities.

Replaces the following old scripts (totaling ~320 lines):
- code/python/fetch_census_shapefiles.py  (131 lines)
    Manual TIGER URL construction, 3 download patterns, BeautifulSoup scraping
- code/python/load_census_shapefiles.py   (61 lines)
    shp2pgsql | psql subprocess pipeline
- code/python/fetch_urbanicity_shapefiles.py
    Similar manual download logic for NCES/urbanicity data
- code/python/load_nces_shapefiles.py
    Similar shp2pgsql loading for NCES

Now: siege_utilities.CensusDataSource handles all discovery, downloading,
and format negotiation. PostGISConnector handles loading.

Example usage:
    from swh.census import download_census_boundaries, load_census_to_postgis

    # Download for Texas
    gdfs = download_census_boundaries(state_fips="48")

    # Download and load directly into PostGIS
    tables = load_census_to_postgis(state_fips="48")
    # tables = {"tabblock20": "tabblock20_48", "sldu": "sldu_48", ...}
"""

from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd

from swh.config import settings

logger = logging.getLogger(__name__)


def download_census_boundaries(
    state_fips: str,
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> dict[str, gpd.GeoDataFrame]:
    """Download Census TIGER boundary files for a state.

    Uses siege_utilities.CensusDataSource which handles:
    - TIGER URL construction (replaces hardcoded URLs with cd116, etc.)
    - Single-file vs state-by-state vs directory-scrape patterns
    - Zip extraction and shapefile reading
    - CRS handling

    Args:
        state_fips: Two-digit FIPS code, e.g. "48" for Texas.
        boundary_types: List of boundary types to download.
            Defaults to settings.census.boundary_types.
            Examples: ["tabblock20", "sldu", "sldl", "cd", "county"]
        year: Census year. Defaults to settings.census.year.

    Returns:
        Dict mapping boundary type name to GeoDataFrame.

    Example:
        >>> gdfs = download_census_boundaries("48", boundary_types=["tabblock20", "county"])
        >>> gdfs["tabblock20"].shape
        (914231, 12)
        >>> gdfs["county"].shape
        (254, 18)
    """
    from siege_utilities.census import CensusDataSource

    year = year or settings.census.year
    boundary_types = boundary_types or settings.census.boundary_types

    cds = CensusDataSource(year=year)
    results = {}

    for boundary_type in boundary_types:
        logger.info("Downloading %s for state FIPS %s (year=%d)", boundary_type, state_fips, year)
        try:
            gdf = cds.get_geographic_boundaries(state_fips, boundary_type)
            results[boundary_type] = gdf
            logger.info("  -> %d features downloaded", len(gdf))
        except Exception:
            logger.exception("Failed to download %s for %s", boundary_type, state_fips)

    return results


def load_census_to_postgis(
    state_fips: str,
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
    connection_string: Optional[str] = None,
    schema: str = "public",
) -> dict[str, str]:
    """Download Census boundaries and load them into PostGIS in one step.

    Replaces the old two-step process:
        1. fetch_census_shapefiles.py  -> download zips to disk
        2. load_census_shapefiles.py   -> shp2pgsql | psql

    Now: siege_utilities handles both download and upload.

    Args:
        state_fips: Two-digit FIPS code.
        boundary_types: List of boundary types. Defaults to config.
        year: Census year. Defaults to config.
        connection_string: SQLAlchemy connection string.
            Defaults to settings.database.connection_string.
        schema: PostGIS schema. Defaults to "public".

    Returns:
        Dict mapping boundary type to table name created in PostGIS.

    Example:
        >>> tables = load_census_to_postgis("48", boundary_types=["tabblock20"])
        >>> tables
        {'tabblock20': 'tabblock20_48'}
    """
    from siege_utilities.connectors import PostGISConnector

    conn_str = connection_string or settings.database.connection_string
    connector = PostGISConnector(conn_str)

    gdfs = download_census_boundaries(state_fips, boundary_types, year)
    tables = {}

    for boundary_type, gdf in gdfs.items():
        table_name = f"{boundary_type}_{state_fips}"
        logger.info("Loading %s -> PostGIS table '%s' (%d features)", boundary_type, table_name, len(gdf))
        connector.upload_spatial_data(gdf, table_name, schema=schema, if_exists="replace")
        tables[boundary_type] = table_name

    return tables


def download_all_states(
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> dict[str, dict[str, gpd.GeoDataFrame]]:
    """Download Census boundaries for all configured states.

    Example:
        >>> all_data = download_all_states(boundary_types=["county"])
        >>> all_data["48"]["county"].shape
        (254, 18)
    """
    state_fips_list = settings.census.get_state_fips_list()
    results = {}

    for fips in state_fips_list:
        logger.info("Processing state FIPS %s", fips)
        results[fips] = download_census_boundaries(fips, boundary_types, year)

    return results


def load_all_states_to_postgis(
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
    connection_string: Optional[str] = None,
    schema: str = "public",
) -> dict[str, dict[str, str]]:
    """Download and load Census boundaries for all configured states into PostGIS.

    Example:
        >>> all_tables = load_all_states_to_postgis(boundary_types=["tabblock20"])
        >>> all_tables["48"]
        {'tabblock20': 'tabblock20_48'}
    """
    state_fips_list = settings.census.get_state_fips_list()
    results = {}

    for fips in state_fips_list:
        logger.info("Processing state FIPS %s", fips)
        results[fips] = load_census_to_postgis(fips, boundary_types, year, connection_string, schema)

    return results
