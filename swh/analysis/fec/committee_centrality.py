"""Compute committee-centrality reports from the FEC campaign-finance graph.

For each requested party affiliation (DEM / REP / etc.), filters the
graph to committees linked to candidates of that affiliation, aggregates
inter-committee transaction amounts, and writes one PostgreSQL table
per party (``committee_centrality_<PARTY>``).

Reads the graph parquet written by ``build_fec_graph`` from the
configured ``FEC_BASE_PATH/<graph_subdir>``; both scripts now share a
single canonical graph directory (pre-modernization they diverged --
``build_graph`` wrote to ``bulk/exports`` and ``committee_centrality``
read from ``graph/``, so the pipeline never ran end-to-end without a
manual file move).

Driven by the ``swh fec-centrality`` CLI command.

Pre-modernization (SW#34) shape -- preserved here for the audit trail:

- Used ``SparkContext(conf=conf) + SQLContext`` (deprecated since 3.0).
- ``WORKING_ON_LAPTOP = False`` boolean toggle on hardcoded paths.
- Read the FEC graph from ``BASE_PATH/graph`` but ``build_graph`` wrote
  to ``BASE_PATH/bulk/exports``. End-to-end was broken without a manual
  move.
- Hardcoded JDBC URL ``jdbc:postgresql://10.10.0.100:30543/electinfo``,
  user ``postgres``, plaintext password literal (since rotated). Now
  read from ``swh.config.settings.database``.
- Imported ``dotenv_values`` for env loading (extra dependency); now
  unified through ``swh.config``.
- Ran as script-with-side-effects-at-import; no function boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

logger = logging.getLogger(__name__)


# Default party affiliations covered by the centrality report. Each entry
# maps a human-readable label to the FEC ``CAND_PTY_AFFILIATION`` code.
DEFAULT_PARTY_FILTERS: dict[str, str] = {
    "democrat":   "DEM",
    "republican": "REP",
}


def compute_party_centrality(
    spark: SparkSession,
    graph,
    party_code: str,
) -> DataFrame:
    """Compute pairwise committee-transaction totals for one party.

    Filters the graph to:

    - Committee vertices linked to a Candidate whose
      ``CAND_PTY_AFFILIATION`` matches ``party_code`` (via the
      OfficialLinkage edge), then
    - Transaction edges among those committees.

    Aggregates by ``(CMTE1_ID, CMTE2_ID)`` and returns a DataFrame
    ordered by ``TOTAL_AMOUNT`` descending.
    """
    from pyspark.sql.functions import col, first
    from pyspark.sql.functions import sum as f_sum

    from graphframes import GraphFrame  # type: ignore[import-not-found]

    cmte_vertex_search = (
        graph.find("(cand)-[link]->(cmte)")
        .filter("link.label = 'OfficialLinkage'")
        .filter("cand.label = 'Candidate'")
        .filter("cmte.label = 'Committee'")
        .filter(f"cand.CAND_PTY_AFFILIATION = '{party_code}'")
    )

    cmte_id_df = cmte_vertex_search.select(col("cmte.CMTE_ID").alias("id"))
    logger.info("Party %s: %d linked committees", party_code, cmte_id_df.count())

    relevant_committees = GraphFrame(
        graph.vertices.join(cmte_id_df, "id", "inner"),
        graph.edges,
    ).dropIsolatedVertices()

    report_search = (
        relevant_committees.find("(cmte1)-[txn]->(cmte2)")
        .filter("txn.label = 'Transaction'")
        .filter("cmte1.label = 'Committee'")
        .filter("cmte2.label = 'Committee'")
    )

    report = (
        report_search.select(
            col("cmte1.CMTE_ID").alias("CMTE1_ID"),
            col("cmte2.CMTE_ID").alias("CMTE2_ID"),
            col("cmte1.CMTE_NM").alias("CMTE1_NAME"),
            col("cmte2.CMTE_NM").alias("CMTE2_NAME"),
            col("txn.TRANSACTION_AMT").alias("TRANSACTION_AMT"),
        )
        .groupBy(col("CMTE1_ID"), col("CMTE2_ID"))
        .agg(
            first(col("CMTE1_NAME")).alias("CMTE1_NAME"),
            first(col("CMTE2_NAME")).alias("CMTE2_NAME"),
            f_sum(col("TRANSACTION_AMT")).alias("TOTAL_AMOUNT"),
        )
        .orderBy(col("TOTAL_AMOUNT").desc())
    )

    return report


def compute_committee_centrality(
    spark: SparkSession,
    graph_input_path: str | Path,
    party_filters: dict[str, str] | None = None,
    jdbc_url: str | None = None,
    jdbc_user: str | None = None,
    jdbc_password: str | None = None,
    jdbc_driver: str = "org.postgresql.Driver",
) -> None:
    """Compute and persist committee-centrality reports.

    Reads the FEC graph parquet from ``graph_input_path`` (the same
    directory ``build_fec_graph`` writes to), computes one
    ``committee_centrality_<PARTY>`` aggregate per entry in
    ``party_filters``, and writes each via JDBC to the configured
    PostgreSQL target.

    JDBC connection parameters default to ``swh.config.settings.database``
    when not passed explicitly. The caller manages the SparkSession
    lifecycle.
    """
    from graphframes import GraphFrame  # type: ignore[import-not-found]

    from swh.config import settings

    party_filters = party_filters if party_filters is not None else DEFAULT_PARTY_FILTERS

    if jdbc_url is None or jdbc_user is None or jdbc_password is None:
        db = settings.database
        jdbc_url = jdbc_url or f"jdbc:postgresql://{db.host}:{db.port}/{db.db}"
        jdbc_user = jdbc_user or db.user
        jdbc_password = jdbc_password or db.password

    graph_input_path = Path(graph_input_path)
    vertices_path = str(graph_input_path / "all_data_vertices.parquet")
    edges_path = str(graph_input_path / "all_data_edges.parquet")

    logger.info("Reading vertices from %s", vertices_path)
    vertices = spark.read.format("parquet").load(vertices_path)
    logger.info("Reading edges from %s", edges_path)
    edges = spark.read.format("parquet").load(edges_path)

    graph = GraphFrame(vertices, edges)
    logger.info(
        "Loaded FEC graph: %d vertices, %d edges",
        graph.vertices.count(), graph.edges.count(),
    )

    for label, party_code in party_filters.items():
        logger.info("Computing centrality report for %s (%s)", label, party_code)
        report_df = compute_party_centrality(spark, graph, party_code)
        row_count = report_df.count()
        logger.info("Party %s: %d aggregate rows", party_code, row_count)

        table_name = f"committee_centrality_{party_code}"
        logger.info("Writing %s to %s", table_name, jdbc_url)
        (
            report_df.write.format("jdbc")
            .mode("overwrite")
            .option("url", jdbc_url)
            .option("driver", jdbc_driver)
            .option("dbtable", table_name)
            .option("user", jdbc_user)
            .option("password", jdbc_password)
            .save()
        )


def main() -> None:
    """CLI shim for direct invocation via ``python -m swh.analysis.fec.committee_centrality``.

    Canonical entry point is the Click command ``swh fec-centrality``;
    this ``main()`` is the thin wrapper.
    """
    import argparse

    from swh.config import settings

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--graph-input-path", default=settings.fec.graph_path,
                        help=f"Graph parquet directory (default: {settings.fec.graph_path})")
    parser.add_argument("--party", action="append", default=None,
                        help="Party code (DEM, REP, ...). May be passed multiple times. "
                             "Default: DEM + REP.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    party_filters = None
    if args.party:
        party_filters = {code.lower(): code for code in args.party}

    spark = settings.spark.build_session()
    try:
        compute_committee_centrality(
            spark=spark,
            graph_input_path=args.graph_input_path,
            party_filters=party_filters,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
