"""
Voter file loading via siege_utilities.

Replaces code/python/load_voters.py (91 lines) which had:
- Pandas chunked CSV with manual to_sql
- Reference to undefined set_environment_variables_from_dict()
- Hardcoded Texas state configuration
- from utilities import * / from settings import *

Now: thin wrapper around siege_utilities + SQLAlchemy bulk loading.

Example usage:
    from swh.voters import load_voter_file

    # Load a voter file CSV into PostGIS
    row_count = load_voter_file(
        filepath="/data/inputs/TX_voters.csv",
        table_name="voters_tx",
    )
    print(f"Loaded {row_count} voters")
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from swh.config import settings

logger = logging.getLogger(__name__)


# Default column names matching TargetSmart voter file format.
# Override these via VoterFileConfig or CLI arguments.
DEFAULT_COLUMNS = {
    "longitude": "vb_tsmart_longitude",
    "latitude": "vb_tsmart_latitude",
    "precinct": "vb_vf_national_precinct_code",
    "county": "vb_tsmart_county_name",
    "cd": "vb_vf_cd",
    "sd": "vb_vf_sd",
    "hd": "vb_vf_hd",
}


def _coerce_and_build_geometry(
    df: pd.DataFrame,
    longitude_col: str,
    latitude_col: str,
    crs: int,
) -> gpd.GeoDataFrame:
    """Coerce lon/lat to numeric, drop invalid rows, build GeoDataFrame.

    Handles non-numeric values (e.g. 'invalid', empty strings) by coercing
    to NaN first, then dropping — prevents Point() from crashing on bad data.
    Also validates coordinate bounds.

    Example:
        >>> df = pd.DataFrame({"lon": ["1.0", "invalid", ""], "lat": ["2.0", "3.0", ""]})
        >>> gdf = _coerce_and_build_geometry(df, "lon", "lat", 4326)
        >>> len(gdf)
        1
    """
    df = df.copy()
    df[longitude_col] = pd.to_numeric(df[longitude_col], errors="coerce")
    df[latitude_col] = pd.to_numeric(df[latitude_col], errors="coerce")
    df = df.dropna(subset=[longitude_col, latitude_col])

    # Bounds check — valid geographic coordinates
    valid_mask = (
        (df[longitude_col].between(-180, 180))
        & (df[latitude_col].between(-90, 90))
    )
    dropped = (~valid_mask).sum()
    if dropped > 0:
        logger.warning("Dropped %d rows with out-of-range coordinates", dropped)
    df = df[valid_mask]

    geometry = gpd.points_from_xy(df[longitude_col], df[latitude_col])
    return gpd.GeoDataFrame(df, geometry=geometry, crs=f"EPSG:{crs}")


def load_voter_file(
    filepath: str | Path,
    table_name: str,
    connection_string: Optional[str] = None,
    longitude_col: str = DEFAULT_COLUMNS["longitude"],
    latitude_col: str = DEFAULT_COLUMNS["latitude"],
    chunk_size: int = 50_000,
    crs: int = 4326,
    schema: str = "public",
) -> int:
    """Load a voter file CSV into PostGIS as a spatial table.

    Reads the CSV in chunks, creates Point geometries from lon/lat columns,
    and uploads to PostGIS using siege_utilities.PostGISConnector.

    Uses a staging table for atomicity — if any chunk fails, the target
    table is left untouched. On success, the staging table is renamed
    to the target.

    Args:
        filepath: Path to the voter file CSV.
        table_name: Target PostGIS table name.
        connection_string: SQLAlchemy connection string.
            Defaults to settings.database.connection_string.
        longitude_col: Column name for longitude.
        latitude_col: Column name for latitude.
        chunk_size: Number of rows per chunk for memory-efficient loading.
        crs: Coordinate reference system EPSG code. Defaults to 4326.
        schema: PostGIS schema. Defaults to "public".

    Returns:
        Total number of rows loaded.

    Example:
        >>> count = load_voter_file(
        ...     "/data/inputs/TX_voters.csv",
        ...     "voters_tx",
        ...     chunk_size=100_000,
        ... )
        >>> print(f"Loaded {count} voters")
        Loaded 15234567 voters
    """
    from siege_utilities.connectors import PostGISConnector
    from sqlalchemy import text

    filepath = Path(filepath)
    conn_str = connection_string or settings.database.connection_string
    connector = PostGISConnector(conn_str)

    # Use a staging table for atomicity
    staging_table = f"_staging_{table_name}_{uuid.uuid4().hex[:8]}"

    total_rows = 0
    first_chunk = True

    try:
        for chunk in pd.read_csv(filepath, chunksize=chunk_size):
            gdf = _coerce_and_build_geometry(chunk, longitude_col, latitude_col, crs)

            if len(gdf) == 0:
                continue

            # Upload: replace on first chunk, append thereafter
            if_exists = "replace" if first_chunk else "append"
            connector.upload_spatial_data(gdf, staging_table, schema=schema, if_exists=if_exists)

            total_rows += len(gdf)
            first_chunk = False
            logger.info("Loaded chunk: %d rows (total: %d)", len(gdf), total_rows)

        # Atomic swap: drop target, rename staging -> target
        with connector.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {schema}.{table_name}"))
            conn.execute(text(f"ALTER TABLE {schema}.{staging_table} RENAME TO {table_name}"))

        logger.info("Finished loading %s -> %s (%d total rows)", filepath.name, table_name, total_rows)

    except Exception:
        # Clean up staging table on failure
        logger.exception("Failed to load %s — cleaning up staging table", filepath.name)
        try:
            with connector.engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {schema}.{staging_table}"))
        except Exception:
            logger.warning("Could not clean up staging table %s", staging_table)
        raise

    return total_rows


def voter_file_to_geodataframe(
    filepath: str | Path,
    longitude_col: str = DEFAULT_COLUMNS["longitude"],
    latitude_col: str = DEFAULT_COLUMNS["latitude"],
    crs: int = 4326,
) -> gpd.GeoDataFrame:
    """Read a voter file CSV into a GeoDataFrame (in-memory, no PostGIS).

    Useful for Tier 3 (GeoPandas-only) processing in Reverberator.

    Args:
        filepath: Path to the voter file CSV.
        longitude_col: Column name for longitude.
        latitude_col: Column name for latitude.
        crs: Coordinate reference system EPSG code.

    Returns:
        GeoDataFrame with Point geometry column.

    Example:
        >>> gdf = voter_file_to_geodataframe("/data/inputs/TX_voters.csv")
        >>> gdf.head()
    """
    df = pd.read_csv(filepath)
    return _coerce_and_build_geometry(df, longitude_col, latitude_col, crs)
