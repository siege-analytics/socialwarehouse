"""Build the FEC campaign-finance graph for a given election cycle.

Reads FEC bulk-data CSVs (Committee Master, Candidate Master, Webl, CCL,
PAS2, OTH) for the cycle, joins them into a single GraphFrame of vertices
(Committee / Candidate / Campaign) and edges (OfficialLinkage /
Transaction), and writes the result as parquet to the configured graph
output directory.

Driven by the ``swh fec-build-graph`` CLI command. Standalone script
invocation (``spark-submit`` / ``python -m swh.analysis.fec.build_graph``)
is supported via the ``main()`` entry point.

Pre-modernization (SW#34) shape — preserved here for the audit trail:

- Used ``SparkContext(conf=conf) + SQLContext`` (deprecated since 3.0).
- Had ``WORKING_ON_LAPTOP = False`` boolean toggling hardcoded
  ``/Volumes/DATA/electinfo`` vs ``/mnt/data/electinfo`` paths.
- ``entityTypeToLabel`` was a broken ``match`` with no return / no
  assignment in the case arms; always returned ``None``. The ``oth``
  edges silently had ``dst = ":" + OTHER_ID`` (no entity label prefix).
- ``DATA_EXPORTS`` was assigned twice on consecutive lines; the second
  assignment shadowed the first. The intended ``BASE_PATH / "graph"``
  destination was dead code.
- Ran as script-with-side-effects-at-import; no function boundary;
  no callable surface for tests.

The modernized form addresses each of these. See SW#34's audit
comment for the full list.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

logger = logging.getLogger(__name__)


# --- Constants ------------------------------------------------------------

FEC_BULK_FILES_DELIMITER = "|"
FEC_HEADER_FILES_DELIMITER = ","
FEC_BULK_FILES_FORMAT = "csv"

# Per-source-table control structure. Each entry:
#   category:       "vertex" or "edge"
#   display_name:   the human-readable label written to every row's
#                   ``label`` column (and used as the vertex-id prefix)
#   header_file:    name of the column-header CSV in BULK_DATA_BASE_PATH
#   data_glob:      glob pattern for the per-cycle data files
PROCESSING_DISPATCHER: dict[str, tuple[str, str, str, str]] = {
    "cm":   ("vertex", "Committee",       "cm_header_file.csv",   "cm**.txt"),
    "cn":   ("vertex", "Candidate",       "cn_header_file.csv",   "cn**.txt"),
    "webl": ("vertex", "Campaign",        "webl_header_file.csv", "webl**.txt"),
    "ccl":  ("edge",   "OfficialLinkage", "ccl_header_file.csv",  "ccl**.txt"),
    "pas2": ("edge",   "Transaction",     "pas2_header_file.csv", "itpas2**.txt"),
    "oth":  ("edge",   "Transaction",     "oth_header_file.csv",  "itoth**.txt"),
}

# FEC ``ENTITY_TP`` codes -> vertex label. The pre-modernization code
# had a broken ``match`` (no return / no assignment); this dict + helper
# replaces it.
ENTITY_TYPE_TO_LABEL: dict[str, str] = {
    "CAN": "Candidate",
    "CCM": "Committee",
    "COM": "Committee",
    "PAC": "Committee",
    "PTY": "Committee",
}


# --- Helpers --------------------------------------------------------------

def entity_type_to_label(entity_type: str | None) -> str:
    """Map an FEC ``ENTITY_TP`` code to the vertex label string.

    Returns the empty string for unknown / null codes (preserves the
    pre-modernization not-found contract: caller's downstream ``concat``
    yielded ``":<OTHER_ID>"`` for unknowns; same shape, but now derived
    from a falsifiable lookup table instead of a broken ``match``).

    >>> entity_type_to_label("CAN")
    'Candidate'
    >>> entity_type_to_label("COM")
    'Committee'
    >>> entity_type_to_label("XXX")
    ''
    >>> entity_type_to_label(None)
    ''
    """
    if not entity_type:
        return ""
    return ENTITY_TYPE_TO_LABEL.get(entity_type, "")


def _load_source_table(
    spark: SparkSession,
    bulk_path: Path,
    cycle: int,
    source_key: str,
    label: str,
    header_file: str,
    data_glob: str,
) -> DataFrame:
    """Load one FEC bulk-data table for ``cycle``, apply column headers,
    and tag every row with the source's ``label`` string."""
    from pyspark.sql.functions import lit

    full_data_glob = str(bulk_path / str(cycle) / data_glob)
    header_path = bulk_path / header_file

    logger.info("Loading %s (%s) from %s", source_key, label, full_data_glob)

    with open(header_path, newline="") as f:
        header_field_names = next(csv.reader(f, delimiter=FEC_HEADER_FILES_DELIMITER))

    if not header_field_names:
        raise ValueError(f"Empty header file {header_path}")

    raw = (
        spark.read.format(FEC_BULK_FILES_FORMAT)
        .option("delimiter", FEC_BULK_FILES_DELIMITER)
        .option("inferSchema", True)
        .load(full_data_glob)
    )

    df = raw.toDF(*header_field_names).withColumn("label", lit(label))
    logger.info("Loaded %s: %d rows", source_key, df.count())
    return df


def _add_vertex_ids(vertex_dfs: dict[str, DataFrame]) -> dict[str, DataFrame]:
    """Add the ``id`` column to every vertex DataFrame.

    Vertex ID format: ``"<Label>:<source-id>"`` (e.g. ``"Committee:C00000123"``).
    The format must match what edges' ``src`` / ``dst`` reference.
    """
    from pyspark.sql.functions import col, concat, lit

    return {
        "cm":   vertex_dfs["cm"].withColumn("id", concat(col("label"), lit(":"), col("CMTE_ID"))),
        "cn":   vertex_dfs["cn"].withColumn("id", concat(col("label"), lit(":"), col("CAND_ID"))),
        "webl": vertex_dfs["webl"].withColumn("id", concat(col("label"), lit(":"), col("CAND_ID"))),
    }


def _add_edge_endpoints(
    spark: SparkSession,
    vertex_dfs: dict[str, DataFrame],
    edge_dfs: dict[str, DataFrame],
) -> dict[str, DataFrame]:
    """Add ``src`` / ``dst`` columns to every edge DataFrame.

    Each edge type derives its endpoints differently:

    - **ccl** (OfficialLinkage): Candidate -> Committee
    - **pas2** (Transaction):    Committee -> Candidate
    - **oth** (Transaction):     Committee -> <entity-type-derived>
    - **webl** (stub):           Candidate -> Campaign, synthesized
                                 from the Candidate vertex set
    """
    from pyspark.sql.functions import col, concat, lit, udf
    from pyspark.sql.types import StringType

    entity_type_udf = udf(entity_type_to_label, StringType())

    result: dict[str, DataFrame] = {}

    result["ccl"] = (
        edge_dfs["ccl"]
        .withColumn("src", concat(lit("Candidate"), lit(":"), col("CAND_ID")))
        .withColumn("dst", concat(lit("Committee"), lit(":"), col("CMTE_ID")))
    )

    result["pas2"] = (
        edge_dfs["pas2"]
        .withColumn("src", concat(lit("Committee"), lit(":"), col("CMTE_ID")))
        .withColumn("dst", concat(lit("Candidate"), lit(":"), col("CAND_ID")))
    )

    result["oth"] = (
        edge_dfs["oth"]
        .withColumn("src", concat(lit("Committee"), lit(":"), col("CMTE_ID")))
        .withColumn(
            "dst",
            concat(entity_type_udf(col("ENTITY_TP")), lit(":"), col("OTHER_ID")),
        )
    )

    # webl is a stub edge: each Candidate vertex has a Campaign vertex of
    # the same id (per the pre-modernization synthesis).
    result["webl"] = vertex_dfs["cn"].select(
        concat(lit("Candidate"), lit(":"), col("CAND_ID")).alias("src"),
        concat(lit("Campaign"), lit(":"), col("CAND_ID")).alias("dst"),
    )

    return result


def _union_partitions(
    spark: SparkSession,
    parts: dict[str, DataFrame],
) -> tuple[DataFrame, int]:
    """Union an arbitrary set of DataFrames by name, allowing missing
    columns. Returns ``(unioned_df, sum_of_individual_counts)``."""
    from pyspark.sql.types import StructType

    union_df: DataFrame = spark.createDataFrame([], StructType([]))
    expected_count = 0
    for _key, df in parts.items():
        expected_count += df.count()
        union_df = union_df.unionByName(df, allowMissingColumns=True)
    return union_df, expected_count


# --- Public entry point ---------------------------------------------------

def build_fec_graph(
    spark: SparkSession,
    cycle: int,
    bulk_path: str | Path,
    graph_output_path: str | Path,
) -> None:
    """Build and persist the FEC campaign-finance graph for ``cycle``.

    Reads FEC bulk-data CSVs from ``bulk_path / str(cycle) / <pattern>``,
    joins them into Committee / Candidate / Campaign vertices and
    OfficialLinkage / Transaction edges, and writes the result as two
    parquet datasets under ``graph_output_path``:

    - ``graph_output_path / "all_data_vertices.parquet"``
    - ``graph_output_path / "all_data_edges.parquet"``

    The caller manages the ``SparkSession`` lifecycle.
    """
    from graphframes import GraphFrame  # type: ignore[import-not-found]

    bulk_path = Path(bulk_path)
    graph_output_path = Path(graph_output_path)
    graph_output_path.mkdir(parents=True, exist_ok=True)

    vertex_dfs: dict[str, DataFrame] = {}
    edge_dfs: dict[str, DataFrame] = {}

    for key, (category, label, header_file, data_glob) in PROCESSING_DISPATCHER.items():
        df = _load_source_table(spark, bulk_path, cycle, key, label, header_file, data_glob)
        if category == "vertex":
            vertex_dfs[key] = df
        elif category == "edge":
            edge_dfs[key] = df
        else:
            raise ValueError(f"Unknown category {category!r} for source {key}")

    vertex_dfs = _add_vertex_ids(vertex_dfs)
    edge_dfs = _add_edge_endpoints(spark, vertex_dfs, edge_dfs)

    vertex_union, vertex_expected = _union_partitions(spark, vertex_dfs)
    edge_union, edge_expected = _union_partitions(spark, edge_dfs)

    if vertex_union.count() != vertex_expected:
        logger.warning(
            "Vertex union count (%d) does not match sum of individual counts (%d). "
            "This may indicate schema-mismatch drops; investigate before relying "
            "on the graph.",
            vertex_union.count(), vertex_expected,
        )
    if edge_union.count() != edge_expected:
        logger.warning(
            "Edge union count (%d) does not match sum of individual counts (%d).",
            edge_union.count(), edge_expected,
        )

    graph = GraphFrame(vertex_union, edge_union)
    logger.info(
        "Built FEC graph for cycle %d: %d vertices, %d edges",
        cycle, graph.vertices.count(), graph.edges.count(),
    )

    edges_out = str(graph_output_path / "all_data_edges.parquet")
    vertices_out = str(graph_output_path / "all_data_vertices.parquet")

    logger.info("Writing edges to %s", edges_out)
    graph.edges.write.format("parquet").mode("overwrite").save(edges_out)

    logger.info("Writing vertices to %s", vertices_out)
    graph.vertices.write.format("parquet").mode("overwrite").save(vertices_out)


def main() -> None:
    """CLI shim for direct invocation via ``python -m swh.analysis.fec.build_graph``.

    The canonical entry point is the Click command ``swh fec-build-graph``
    in ``swh.cli``; this ``main()`` is a thin wrapper that reads settings
    from the environment and delegates.
    """
    import argparse

    from swh.config import settings

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cycle", type=int, default=2024,
                        help="Election cycle first year (default: 2024)")
    parser.add_argument("--bulk-path", default=settings.fec.bulk_path,
                        help=f"FEC bulk-data directory (default: {settings.fec.bulk_path})")
    parser.add_argument("--graph-output-path", default=settings.fec.graph_path,
                        help=f"Graph output directory (default: {settings.fec.graph_path})")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    spark = settings.spark.build_session()
    try:
        build_fec_graph(
            spark=spark,
            cycle=args.cycle,
            bulk_path=args.bulk_path,
            graph_output_path=args.graph_output_path,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
