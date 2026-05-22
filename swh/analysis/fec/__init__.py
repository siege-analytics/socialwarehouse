"""FEC Campaign Finance Graph Analysis.

Uses PySpark and GraphFrames to build and analyze campaign contribution networks.

Scripts:
    build_graph: Constructs a graph from FEC bulk data (committees, candidates, contributions)
    committee_centrality: Computes centrality metrics (PageRank, degree) on the campaign finance graph

Usage:
    These scripts require the Spark Docker profile:
        make up-spark
        make spark-shell
        spark-submit swh/analysis/fec/build_graph.py --cycle 2024
"""
