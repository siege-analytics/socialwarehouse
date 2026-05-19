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
from typing import NamedTuple, Optional

import geopandas as gpd

from swh.config import settings

logger = logging.getLogger(__name__)


class DownloadResult(NamedTuple):
    """Structured return for the download_* functions.

    Pre-S1/#131 the download functions returned just `dict[str, GeoDataFrame]`,
    so per-boundary-type failures were logged but invisible to callers --
    callers saw a `results` dict missing the failed keys and had no way to
    know whether the gap was "not requested" or "requested but failed."
    """

    successes: dict[str, gpd.GeoDataFrame]  # boundary_type -> GeoDataFrame
    failures: dict[str, Exception]  # boundary_type -> exception that fired

    @property
    def any_failed(self) -> bool:
        return bool(self.failures)

    @property
    def all_failed(self) -> bool:
        return bool(self.failures) and not self.successes


class LoadResult(NamedTuple):
    """Structured return for the load_*_to_postgis functions.

    Mirrors DownloadResult shape: successes map to created table names;
    failures map to whatever went wrong (download error or upload error).
    """

    successes: dict[str, str]  # boundary_type -> created table name
    failures: dict[str, Exception]  # boundary_type -> exception that fired

    @property
    def any_failed(self) -> bool:
        return bool(self.failures)


def download_census_boundaries(
    state_fips: str,
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> DownloadResult:
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
        DownloadResult (NamedTuple of successes + failures). Per-boundary-type
        failures are caught + recorded; the function does NOT raise on
        partial failure. Callers should check ``result.any_failed`` and act
        accordingly. (S1 / SW#131)

    Example:
        >>> result = download_census_boundaries("48", boundary_types=["tabblock20", "county"])
        >>> result.successes["tabblock20"].shape
        (914231, 12)
        >>> if result.any_failed:
        ...     for bt, err in result.failures.items():
        ...         print(f"Failed {bt}: {err}")
    """
    from siege_utilities.census import CensusDataSource

    year = year or settings.census.year
    boundary_types = boundary_types or settings.census.boundary_types

    cds = CensusDataSource(year=year)
    successes: dict[str, gpd.GeoDataFrame] = {}
    failures: dict[str, Exception] = {}

    for boundary_type in boundary_types:
        logger.info("Downloading %s for state FIPS %s (year=%d)", boundary_type, state_fips, year)
        try:
            gdf = cds.get_geographic_boundaries(state_fips, boundary_type)
            successes[boundary_type] = gdf
            logger.info("  -> %d features downloaded", len(gdf))
        except Exception as e:
            logger.exception("Failed to download %s for %s", boundary_type, state_fips)
            failures[boundary_type] = e

    return DownloadResult(successes=successes, failures=failures)


def load_census_to_postgis(
    state_fips: str,
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
    connection_string: Optional[str] = None,
    schema: str = "public",
) -> LoadResult:
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
        LoadResult (NamedTuple of successes + failures). Successes map
        boundary_type -> created table name; failures map boundary_type
        -> the exception that fired (either at download or upload time).
        Callers should check ``result.any_failed``. (S1 / SW#131)

    Example:
        >>> result = load_census_to_postgis("48", boundary_types=["tabblock20"])
        >>> result.successes
        {'tabblock20': 'tabblock20_48'}
        >>> if result.any_failed:
        ...     print(f"{len(result.failures)} boundary types failed")
    """
    from siege_utilities.geo.spatial_transformations import PostGISConnector

    conn_str = connection_string or settings.database.connection_string
    connector = PostGISConnector(conn_str)

    download = download_census_boundaries(state_fips, boundary_types, year)
    successes: dict[str, str] = {}
    failures: dict[str, Exception] = dict(download.failures)

    for boundary_type, gdf in download.successes.items():
        table_name = f"{boundary_type}_{state_fips}"
        logger.info("Loading %s -> PostGIS table '%s' (%d features)", boundary_type, table_name, len(gdf))
        try:
            ok = connector.upload_spatial_data(gdf, table_name, schema=schema, if_exists="replace")
            if ok:
                successes[boundary_type] = table_name
            else:
                # upload_spatial_data returns False on failure without raising.
                failures[boundary_type] = RuntimeError(
                    f"upload_spatial_data returned False for {table_name}"
                )
        except Exception as e:
            logger.exception("Failed to upload %s -> %s", boundary_type, table_name)
            failures[boundary_type] = e

    return LoadResult(successes=successes, failures=failures)


def download_all_states(
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> dict[str, DownloadResult]:
    """Download Census boundaries for all configured states.

    Returns one DownloadResult per state (S1 / SW#131). Callers iterate
    state -> result; each result has its own successes/failures dicts.

    Example:
        >>> all_results = download_all_states(boundary_types=["county"])
        >>> all_results["48"].successes["county"].shape
        (254, 18)
        >>> total_failed = sum(len(r.failures) for r in all_results.values())
    """
    state_fips_list = settings.census.get_state_fips_list()
    results: dict[str, DownloadResult] = {}

    for fips in state_fips_list:
        logger.info("Processing state FIPS %s", fips)
        results[fips] = download_census_boundaries(fips, boundary_types, year)

    return results


def load_all_states_to_postgis(
    boundary_types: Optional[list[str]] = None,
    year: Optional[int] = None,
    connection_string: Optional[str] = None,
    schema: str = "public",
) -> dict[str, LoadResult]:
    """Download and load Census boundaries for all configured states into PostGIS.

    Returns one LoadResult per state (S1 / SW#131). Callers iterate
    state -> result; each result has its own successes/failures dicts.

    Example:
        >>> all_results = load_all_states_to_postgis(boundary_types=["tabblock20"])
        >>> all_results["48"].successes
        {'tabblock20': 'tabblock20_48'}
    """
    state_fips_list = settings.census.get_state_fips_list()
    results: dict[str, LoadResult] = {}

    for fips in state_fips_list:
        logger.info("Processing state FIPS %s", fips)
        results[fips] = load_census_to_postgis(fips, boundary_types, year, connection_string, schema)

    return results
