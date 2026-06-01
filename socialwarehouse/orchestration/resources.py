"""Dagster ConfigurableResource definitions for socialwarehouse.

Resources wrap existing socialwarehouse infrastructure:

- ``SparkResource`` wraps ``socialwarehouse.delta.config.get_spark_session()``.
- ``PostGISResource`` wraps the Django default DB connection (SQLAlchemy
  engine over the same Postgres+PostGIS that Django uses).
- ``WarehouseConfig`` carries vintage / catalog / root / partition
  context that the same asset graph can be re-bound to per instance
  project (US-warehouse, UK-warehouse, etc.) without code changes.

Instance projects override these by passing a different
``WarehouseConfig`` value to ``Definitions(resources=...)`` in their
own ``definitions.py`` (see ``docs/orchestration/instance-project-guide.md``).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from dagster import ConfigurableResource, InitResourceContext
from pydantic import Field


class WarehouseConfig(ConfigurableResource):
    """Instance-level warehouse configuration.

    Override per instance project by constructing a different value
    and passing it to ``Definitions(resources={"warehouse": WarehouseConfig(...)})``.

    All fields default to the same env vars ``socialwarehouse.delta.config``
    reads, so by default the Dagster orchestration and the existing
    Django + Spark code see the same warehouse.
    """

    warehouse_root: str = Field(
        default_factory=lambda: os.environ.get("SW_WAREHOUSE_ROOT", "s3a://socialwarehouse"),
        description="Root path for Delta tables (e.g. 's3a://socialwarehouse', 'file:///tmp/sw-warehouse').",
    )
    catalog: str = Field(
        default_factory=lambda: os.environ.get("SW_CATALOG", "socialwarehouse"),
        description="Catalog name (logical namespace for tables; instance projects override).",
    )
    vintage: int = Field(
        default_factory=lambda: int(os.environ.get("SW_VINTAGE", "2020")),
        description="Default Census vintage / data-year for asset materialization. Overridable per run.",
    )
    partition_state: Optional[str] = Field(
        default=None,
        description="Optional state code to partition runs by (e.g. 'TX'). None = full-warehouse run.",
    )


class SparkResource(ConfigurableResource):
    """Dagster resource wrapping ``delta.config.get_spark_session()``.

    Does NOT reinvent the Spark session — defers to the canonical
    socialwarehouse function so config drift between Dagster and the
    Django/CLI paths is impossible by construction.
    """

    app_name: str = Field(
        default="socialwarehouse-orchestration",
        description="Spark application name. Only the FIRST call's app_name takes effect for the JVM session (standard Spark behavior).",
    )
    enable_sedona: bool = Field(
        default=True,
        description="Register Apache Sedona spatial extensions. Default True because most SW assets are spatial.",
    )

    @contextmanager
    def session(self, context: Optional[InitResourceContext] = None) -> Iterator["SparkSession"]:  # noqa: F821 — typed at use site
        """Yield a SparkSession; idempotent via Spark's own builder.getOrCreate().

        The yielded session is NOT stopped on context exit — Spark's
        singleton lives for the JVM lifetime, and stopping it here
        would break the next asset in the same run. See SW#126 rationale
        in delta/config.py.
        """
        from socialwarehouse.delta.config import get_spark_session

        spark = get_spark_session(app_name=self.app_name, enable_sedona=self.enable_sedona)
        try:
            yield spark
        finally:
            pass  # intentional: see docstring


class PostGISResource(ConfigurableResource):
    """Dagster resource exposing a SQLAlchemy engine bound to Django's default DB.

    Reads the connection from ``django.conf.settings.DATABASES['default']``
    so Dagster sees the same Postgres+PostGIS instance Django sees,
    regardless of how the env vars are wired in a given instance
    project. Settings module is read from the ``DJANGO_SETTINGS_MODULE``
    env var (the standard Django entry point); the resource does NOT
    re-implement settings resolution.

    Requires ``DJANGO_SETTINGS_MODULE`` to be set before the resource is
    initialized. In ``dagster dev`` runs, set it via ``.env`` or the
    Dagster code-location env config.
    """

    application_name: str = Field(
        default="socialwarehouse-orchestration",
        description="Postgres application_name for connection identification in pg_stat_activity.",
    )
    statement_timeout_ms: int = Field(
        default=300_000,
        description="Postgres statement_timeout in milliseconds (default 5 min). Long-running materializations should override per-asset.",
    )

    def _make_engine(self) -> "Engine":  # noqa: F821
        """Build a SQLAlchemy engine bound to Django's default DB."""
        import django

        if not django.apps.apps.ready:
            django.setup()

        from django.conf import settings
        from sqlalchemy import create_engine

        db = settings.DATABASES["default"]
        url = (
            f"postgresql+psycopg2://{db['USER']}:{db['PASSWORD']}"
            f"@{db['HOST']}:{db.get('PORT', 5432)}/{db['NAME']}"
        )
        return create_engine(
            url,
            connect_args={
                "application_name": self.application_name,
                "options": f"-c statement_timeout={self.statement_timeout_ms}",
            },
        )

    @contextmanager
    def engine(self) -> Iterator["Engine"]:  # noqa: F821 — typed at use site
        """Yield a SQLAlchemy engine bound to Django's default DB.

        Engine is disposed on context exit (connection-pool cleanup).
        Long-running materializations should hold the engine for the
        full asset and not open/close per-row.
        """
        engine = self._make_engine()
        try:
            yield engine
        finally:
            engine.dispose()

    @contextmanager
    def raw_connection(self) -> Iterator:
        """Yield a raw psycopg2 connection for COPY operations.

        The connection comes from a fresh SQLAlchemy engine's pool.
        Caller is responsible for commit/rollback; the connection and
        engine are cleaned up on context exit.
        """
        engine = self._make_engine()
        conn = engine.raw_connection()
        try:
            yield conn
        finally:
            conn.close()
            engine.dispose()
