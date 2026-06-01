"""Domain assets for the socialwarehouse Dagster code location.

Each domain module declares the bronze->silver->gold assets for one
domain (geo, civic, demographic, economic). Instance projects add
their own per-domain modules following the same pattern; see
``docs/orchestration/instance-project-guide.md``.
"""

from socialwarehouse.orchestration.assets import economic, geo

__all__ = ["economic", "geo"]
