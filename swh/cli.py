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

logger = logging.getLogger("swh")


def _configure_cli_logging():
    """Configure root logging for CLI invocations only.

    Pre-S5/SW#135 fix: logging.basicConfig ran at module import. Any
    importer of swh.cli (tests, notebooks, downstream packages) had
    their root logger silently reconfigured as a side effect of import,
    overriding handlers/levels they had already set. Now: the call is
    gated behind the CLI group callback so it runs only when this
    module is actually being driven as a CLI (via `python -m swh.cli`
    or the `__main__` block), not on every import.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@click.group()
@click.version_option(package_name="socialwarehouse")
def cli():
    """Social Warehouse — data loading CLI powered by siege_utilities."""
    _configure_cli_logging()


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

    Exits non-zero if any per-boundary-type download fails (S1 / #131).

    Examples:
        swh download-census --state 48
        swh download-census --state 48 --state 06 -b tabblock20 -b county
        swh download-census --all-states
    """
    from swh.census import download_census_boundaries, download_all_states

    boundary_types = list(boundary_type) if boundary_type else None
    total_failed = 0

    if all_states:
        all_results = download_all_states(boundary_types=boundary_types, year=year)
        for fips, result in all_results.items():
            if result.any_failed:
                click.echo(
                    f"State {fips}: {len(result.successes)} ok, "
                    f"{len(result.failures)} failed -- {list(result.failures.keys())}",
                    err=True,
                )
                total_failed += len(result.failures)
    elif state:
        for s in state:
            result = download_census_boundaries(s.zfill(2), boundary_types=boundary_types, year=year)
            if result.any_failed:
                click.echo(
                    f"State {s}: {len(result.successes)} ok, "
                    f"{len(result.failures)} failed -- {list(result.failures.keys())}",
                    err=True,
                )
                total_failed += len(result.failures)
    else:
        click.echo("Provide --state <FIPS> or --all-states")
        sys.exit(1)

    if total_failed:
        click.echo(f"Total per-boundary-type failures: {total_failed}", err=True)
        sys.exit(2)


@cli.command("load-census")
@click.option("--state", "-s", multiple=True, help="State FIPS code(s)")
@click.option("--all-states", is_flag=True, help="Load for all configured states")
@click.option("--year", "-y", type=int, default=None, help="Census year")
@click.option("--boundary-type", "-b", multiple=True, help="Boundary type(s)")
@click.option("--schema", default="public", help="PostGIS schema (default: public)")
def load_census(state, all_states, year, boundary_type, schema):
    """Download Census boundaries and load into PostGIS.

    Exits non-zero if any per-boundary-type download or upload fails
    (S1 / #131).

    Examples:
        swh load-census --state 48
        swh load-census --all-states --schema census
    """
    from swh.census import load_census_to_postgis, load_all_states_to_postgis

    boundary_types = list(boundary_type) if boundary_type else None
    total_failed = 0

    if all_states:
        all_results = load_all_states_to_postgis(
            boundary_types=boundary_types, year=year, schema=schema
        )
        total_ok = sum(len(r.successes) for r in all_results.values())
        click.echo(f"Loaded {total_ok} tables across {len(all_results)} states")
        for fips, result in all_results.items():
            if result.any_failed:
                click.echo(
                    f"State {fips}: failures -- {list(result.failures.keys())}",
                    err=True,
                )
                total_failed += len(result.failures)
    elif state:
        for s in state:
            result = load_census_to_postgis(
                s.zfill(2), boundary_types=boundary_types, year=year, schema=schema
            )
            click.echo(f"State {s}: loaded {len(result.successes)} tables")
            if result.any_failed:
                click.echo(
                    f"State {s}: failures -- {list(result.failures.keys())}",
                    err=True,
                )
                total_failed += len(result.failures)
    else:
        click.echo("Provide --state <FIPS> or --all-states")
        sys.exit(1)

    if total_failed:
        click.echo(f"Total per-boundary-type failures: {total_failed}", err=True)
        sys.exit(2)


@cli.command("load-voters")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--table", "-t", required=True, help="Target PostGIS table name")
@click.option("--lon-col", default="vb_tsmart_longitude", help="Longitude column name")
@click.option("--lat-col", default="vb_tsmart_latitude", help="Latitude column name")
@click.option("--chunk-size", default=50_000, type=int, help="Rows per chunk")
@click.option("--schema", default="public", help="PostGIS schema")
@click.option(
    "--encoding", default="utf-8-sig",
    help="CSV encoding. Default utf-8-sig handles BOM in TargetSmart exports.",
)
@click.option(
    "--targetsmart-dtypes/--no-targetsmart-dtypes", default=True,
    help=(
        "Pass TARGETSMART_DEFAULT_DTYPES to pandas so ID columns "
        "(precinct, cd, sd, hd, county, zip) keep leading zeros. "
        "Disable for non-TargetSmart files. (S2 / #132)"
    ),
)
def load_voters(filepath, table, lon_col, lat_col, chunk_size, schema, encoding, targetsmart_dtypes):
    """Load a voter file CSV into PostGIS.

    Examples:
        swh load-voters /data/inputs/TX_voters.csv --table voters_tx
        swh load-voters /data/inputs/VA_voters.csv -t voters_va --chunk-size 100000
        swh load-voters /data/inputs/non_ts_voters.csv -t voters_x --no-targetsmart-dtypes
    """
    from swh.voters import load_voter_file, TARGETSMART_DEFAULT_DTYPES

    dtype = TARGETSMART_DEFAULT_DTYPES if targetsmart_dtypes else None

    count = load_voter_file(
        filepath=filepath,
        table_name=table,
        longitude_col=lon_col,
        latitude_col=lat_col,
        chunk_size=chunk_size,
        schema=schema,
        encoding=encoding,
        dtype=dtype,
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
    click.echo(f"Spark master:    {settings.spark.master}")
    click.echo(f"Spark app:       {settings.spark.app_name}")
    click.echo(f"FEC bulk path:   {settings.fec.bulk_path}")
    click.echo(f"FEC graph path:  {settings.fec.graph_path}")


@cli.command("fec-build-graph")
@click.option("--cycle", "-c", type=int, default=2024,
              help="Election cycle first year (default: 2024)")
@click.option("--bulk-path", default=None,
              help="FEC bulk-data directory. Default: settings.fec.bulk_path "
                   "(typically /mnt/data/electinfo/bulk).")
@click.option("--graph-output-path", default=None,
              help="Graph output directory. Default: settings.fec.graph_path "
                   "(typically /mnt/data/electinfo/graph).")
def fec_build_graph(cycle, bulk_path, graph_output_path):
    """Build the FEC campaign-finance graph for an election cycle.

    Reads FEC bulk-data CSVs from ``<bulk-path>/<cycle>/`` and writes
    vertices + edges parquet to ``<graph-output-path>``. Requires the
    Spark profile (run `make up-spark` first if Docker-based).

    Example:
        swh fec-build-graph --cycle 2024
        swh fec-build-graph --cycle 2022 --bulk-path /data/electinfo/bulk
    """
    from swh.analysis.fec.build_graph import build_fec_graph

    bulk_path = bulk_path or settings.fec.bulk_path
    graph_output_path = graph_output_path or settings.fec.graph_path

    click.echo(f"Building FEC graph: cycle={cycle}, bulk={bulk_path}, out={graph_output_path}")
    spark = settings.spark.build_session()
    try:
        build_fec_graph(
            spark=spark,
            cycle=cycle,
            bulk_path=bulk_path,
            graph_output_path=graph_output_path,
        )
    finally:
        spark.stop()
    click.echo("FEC graph built.")


@cli.command("fec-centrality")
@click.option("--graph-input-path", default=None,
              help="Directory containing the graph parquet written by "
                   "fec-build-graph. Default: settings.fec.graph_path.")
@click.option("--party", "-p", multiple=True, default=None,
              help="Party code (DEM, REP, etc.). May be passed multiple "
                   "times. Default: DEM + REP.")
def fec_centrality(graph_input_path, party):
    """Compute committee-centrality reports per party affiliation.

    For each requested party, filters the FEC graph to its linked
    committees, aggregates inter-committee transaction amounts, and
    writes ``committee_centrality_<PARTY>`` to PostgreSQL via JDBC
    using settings.database connection info.

    Example:
        swh fec-centrality
        swh fec-centrality --party DEM --party REP --party IND
    """
    from swh.analysis.fec.committee_centrality import compute_committee_centrality

    graph_input_path = graph_input_path or settings.fec.graph_path
    party_filters = {p.lower(): p for p in party} if party else None

    click.echo(f"Computing FEC centrality: graph={graph_input_path}, parties={party or 'DEM, REP'}")
    spark = settings.spark.build_session()
    try:
        compute_committee_centrality(
            spark=spark,
            graph_input_path=graph_input_path,
            party_filters=party_filters,
        )
    finally:
        spark.stop()
    click.echo("FEC centrality reports written.")


@cli.command("ingest-voter-file")
@click.option("--vendor", type=click.Choice(["ts"]), required=True, help="Vendor format (currently only 'ts'; L2/Catalist/PDI follow in sub-issues C-E of #250)")
@click.option("--file", "csv_path", type=click.Path(exists=True), required=True, help="Path to the vendor's voter-file CSV")
@click.option("--state", required=True, help="2-char USPS state code (e.g. TX); becomes the bronze partition key")
@click.option("--skip-silver", is_flag=True, default=False, help="Run bronze ingest only; skip the silver.persons build (for staged loads)")
@click.option("--include-scores", is_flag=True, default=False, help="Also extract silver.person_scores from the bronze rows (B.2 of #250)")
@click.option("--include-vote-history", is_flag=True, default=False, help="Also extract silver.vote_history + compute Person aggregates (B.3 of #250)")
@click.option("--methodology", default="ts-2024", show_default=True, help="Methodology label for static TS scores (cycle-aligned scores embed their cycle year)")
def ingest_voter_file(vendor, csv_path, state, skip_silver, include_scores, include_vote_history, methodology):
    """Ingest a vendor voter file through the medallion pipeline.

    Currently supports TargetSmart format. Vendor CSV -> bronze.voter_file_<vendor>
    (raw row as JSON) -> silver.persons (canonical, vendor-neutral).

    Score extraction and vote-history extraction land in sub-issues B.2 / B.3
    of #250; PostGIS materialization lands in B.4. This command is the
    thin spine that puts canonical rows in silver.persons for #257.

    Example:
        swh ingest-voter-file --vendor ts --file /data/inputs/TX_voters.csv --state TX
    """
    if vendor != "ts":
        raise click.UsageError(f"Vendor {vendor!r} is not yet supported; only 'ts' ships in #257.")

    from swh.voters.ts import (
        build_silver_persons,
        compute_aggregates,
        extract_scores,
        extract_vote_history,
        ingest_bronze,
    )

    click.echo(f"Bronze ingest: vendor={vendor} file={csv_path} state={state}")
    spark = settings.spark.build_session()
    try:
        n_bronze = ingest_bronze(spark, csv_path=csv_path, state=state)
        click.echo(f"Bronze rows appended: {n_bronze}")
        if not skip_silver:
            n_silver = build_silver_persons(spark)
            click.echo(f"Silver persons upserted: {n_silver}")
            if include_scores:
                n_scores = extract_scores(spark, default_methodology=methodology)
                click.echo(f"Silver scores upserted: {n_scores}")
            if include_vote_history:
                n_history = extract_vote_history(spark)
                click.echo(f"Silver vote-history rows upserted: {n_history}")
                n_agg = compute_aggregates(spark)
                click.echo(f"Person aggregates updated: {n_agg}")
    finally:
        spark.stop()


@cli.group("materialize-electoral")
def materialize_electoral():
    """Materialize silver electoral Delta tables into PostGIS star schema (B.4 of #250)."""


@materialize_electoral.command("persons")
def materialize_electoral_persons():
    """Materialize silver.persons -> DimPerson."""
    from swh.voters.materialize import materialize_persons
    spark = settings.spark.build_session()
    try:
        n = materialize_persons(spark)
        click.echo(f"DimPerson rows upserted: {n}")
    finally:
        spark.stop()


@materialize_electoral.command("scores")
def materialize_electoral_scores():
    """Materialize silver.person_scores -> FactPersonScore."""
    from swh.voters.materialize import materialize_scores
    spark = settings.spark.build_session()
    try:
        n = materialize_scores(spark)
        click.echo(f"FactPersonScore rows upserted: {n}")
    finally:
        spark.stop()


@materialize_electoral.command("vote-history")
def materialize_electoral_vote_history():
    """Materialize silver.vote_history -> FactVoteHistory."""
    from swh.voters.materialize import materialize_vote_history
    spark = settings.spark.build_session()
    try:
        n = materialize_vote_history(spark)
        click.echo(f"FactVoteHistory rows upserted: {n}")
    finally:
        spark.stop()


@materialize_electoral.command("all")
def materialize_electoral_all():
    """Materialize all three electoral tables in dependency order."""
    from swh.voters.materialize import materialize_all
    spark = settings.spark.build_session()
    try:
        counts = materialize_all(spark)
        click.echo(f"Materialization complete: {counts}")
    finally:
        spark.stop()


@materialize_electoral.command("backfill-addresses")
@click.option("--tolerance", type=float, default=0.00001, show_default=True, help="Degrees tolerance for lat/lon match (~1m at the equator)")
def materialize_electoral_backfill_addresses(tolerance):
    """Backfill silver.persons.address_id + DimPerson.address from lat/lon."""
    from swh.voters.address_backfill import backfill_addresses
    spark = settings.spark.build_session()
    try:
        counts = backfill_addresses(spark, tolerance=tolerance)
        click.echo(f"Address backfill complete: {counts}")
    finally:
        spark.stop()


if __name__ == "__main__":
    cli()
