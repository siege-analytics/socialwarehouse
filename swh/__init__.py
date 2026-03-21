"""
Social Warehouse (swh) — Docker infrastructure + data loading for Siege Analytics.

This package provides thin CLI wrappers around siege_utilities to populate
a PostGIS warehouse with Census boundaries, voter files, and other
geospatial datasets.

Architecture:
    Social Warehouse = infrastructure (Docker containers: PostGIS, Spark, Sedona)
    siege_utilities  = the "verbs" that populate the warehouse
    reverberator     = a second set of "verbs" that analyze the data
"""

__version__ = "1.0.0"
