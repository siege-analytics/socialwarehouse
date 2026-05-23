"""Dagster orchestration layer for socialwarehouse.

This subpackage owns the warehouse pipeline orchestration: scheduled
bronze->silver->gold Delta refreshes, sensor-driven backfills, and
Delta->PostGIS materialization. It is **separate from Celery** in
``socialwarehouse.celery_app`` — Celery handles web-app-triggered async
tasks (geocoding requests, API jobs); Dagster handles warehouse
pipeline orchestration. They coexist without overlap.

Dependencies are an optional extra. Install with::

    pip install socialwarehouse[orchestration]

Entry point for the Dagster UI / CLI::

    dagster dev -m socialwarehouse.orchestration

Adding a new domain to your warehouse (instance projects):
see ``docs/orchestration/instance-project-guide.md``.
"""

from socialwarehouse.orchestration.definitions import defs

__all__ = ["defs"]
