"""
Social Warehouse CLI — thin command-line interface for data loading.

Replaces the old workflow of running individual Python scripts:
    python code/python/ensure_paths.py
    python code/python/fetch_census_shapefiles.py
    python code/python/load_census_shapefiles.py
    python code/python/load_voters.py

Now: `python -m swh.cli <command>` or via Makefile targets.

Example usage:
    # Download Census boundaries for Texas
    python -m swh.cli download-census --state 48

    # Download and load into PostGIS in one step
    python -m swh.cli load-census --state 48

    # Load all configured states
    python -m swh.cli load-census --all

    # Load a voter file
    python -m swh.cli load-voters /data/inputs/TX_voters.csv --table voters_tx

    # Show current configuration
    python -m swh.cli info
"""

from __future__ import annotations

import logging
import sys

import click

from swh.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("swh")


@click.group()
@click.version_option(package_name="socialwarehouse")
def cli():
    """Social Warehouse — data loading CLI powered by siege_utilities."""
    pass


@cli.command("download-census")
@click.option("--state", "-s", multiple=True, help="State FIPS code(s), e.g. 48 06 36")
@click.option("--all-states", is_flag=True, help="Download for all configured states")
@click.option("--year", "-y", type=int, default=None, help="Census year (default: from config)")
@click.option(
    "--boundary-type", "-b", multiple=True,
    help="Boundary type(s) to download, e.g. tabblock20 sldu cd",
)
def download_census(state, all_states, year, boundary_type):
    """Download Census TIGER shapefiles.

    Examples:
        swh download-census --state 48
        swh download-census --state 48 --state 06 -b tabblock20 -b county
        swh download-census --all-states
    """
    from swh.census import download_census_boundaries, download_all_states

    boundary_types = list(boundary_type) if boundary_type else None

    if all_states:
        download_all_states(boundary_types=boundary_types, year=year)
    elif state:
        for s in state:
            download_census_boundaries(s.zfill(2), boundary_types=boundary_types, year=year)
    else:
        click.echo("Provide --state <FIPS> or --all-states")
        sys.exit(1)


@cli.command("load-census")
@click.option("--state", "-s", multiple=True, help="State FIPS code(s)")
@click.option("--all-states", is_flag=True, help="Load for all configured states")
@click.option("--year", "-y", type=int, default=None, help="Census year")
@click.option("--boundary-type", "-b", multiple=True, help="Boundary type(s)")
@click.option("--schema", default="public", help="PostGIS schema (default: public)")
def load_census(state, all_states, year, boundary_type, schema):
    """Download Census boundaries and load into PostGIS.

    Examples:
        swh load-census --state 48
        swh load-census --all-states --schema census
    """
    from swh.census import load_census_to_postgis, load_all_states_to_postgis

    boundary_types = list(boundary_type) if boundary_type else None

    if all_states:
        tables = load_all_states_to_postgis(boundary_types=boundary_types, year=year, schema=schema)
        total = sum(len(v) for v in tables.values())
        click.echo(f"Loaded {total} tables across {len(tables)} states")
    elif state:
        for s in state:
            tables = load_census_to_postgis(s.zfill(2), boundary_types=boundary_types, year=year, schema=schema)
            click.echo(f"State {s}: loaded {len(tables)} tables")
    else:
        click.echo("Provide --state <FIPS> or --all-states")
        sys.exit(1)


@cli.command("load-voters")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--table", "-t", required=True, help="Target PostGIS table name")
@click.option("--lon-col", default="vb_tsmart_longitude", help="Longitude column name")
@click.option("--lat-col", default="vb_tsmart_latitude", help="Latitude column name")
@click.option("--chunk-size", default=50_000, type=int, help="Rows per chunk")
@click.option("--schema", default="public", help="PostGIS schema")
def load_voters(filepath, table, lon_col, lat_col, chunk_size, schema):
    """Load a voter file CSV into PostGIS.

    Examples:
        swh load-voters /data/inputs/TX_voters.csv --table voters_tx
        swh load-voters /data/inputs/VA_voters.csv -t voters_va --chunk-size 100000
    """
    from swh.voters import load_voter_file

    count = load_voter_file(
        filepath=filepath,
        table_name=table,
        longitude_col=lon_col,
        latitude_col=lat_col,
        chunk_size=chunk_size,
        schema=schema,
    )
    click.echo(f"Loaded {count:,} voters into '{table}'")


@cli.command("info")
def info():
    """Show current Social Warehouse configuration.

    Example:
        swh info
    """
    click.echo("Social Warehouse Configuration")
    click.echo("=" * 40)
    click.echo(f"Database host:   {settings.database.host}")
    click.echo(f"Database name:   {settings.database.db}")
    click.echo(f"Database user:   {settings.database.user}")
    click.echo(f"Census year:     {settings.census.year}")
    click.echo(f"Congress:        {settings.census.congress_number}")
    click.echo(f"States:          {settings.census.states}")
    click.echo(f"Boundary types:  {', '.join(settings.census.boundary_types)}")


if __name__ == "__main__":
    cli()
