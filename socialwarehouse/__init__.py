"""
Socialwarehouse — data warehouse and delta lake for geographic, demographic, and civic data.

This is the DSTK (Data Science Toolkit) replacement: a deployable application that uses
siege_utilities' geographic verbs to operate geocoding, boundary management, and Census
data warehousing at massive scale.

Architecture:
    siege_utilities  = kitchen equipment — single-serving geographic operations
    socialwarehouse  = the restaurant — bulk geocoding, temporal boundaries, star schema,
                       DSTK REST API, Delta Lake + Spark orchestration
"""

__version__ = "2.0.0-dev"
