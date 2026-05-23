"""Sanity tests for the orchestration resources.

These tests verify the resource classes import correctly, accept
their declared config fields, and resolve env-var defaults. They do
NOT actually open a SparkSession or a DB connection — that requires
the spark + postgis extras and a live cluster + DB, and belongs in
an integration test suite.

Skipped when ``dagster`` is not installed (the [orchestration] extra
is opt-in).
"""

from __future__ import annotations

import os

import pytest

dagster = pytest.importorskip("dagster")


def test_resources_module_imports():
    """resources module imports without raising."""
    from socialwarehouse.orchestration import resources  # noqa: F401


def test_warehouse_config_reads_env_defaults(monkeypatch):
    """WarehouseConfig picks up SW_* env vars when constructed without args."""
    monkeypatch.setenv("SW_WAREHOUSE_ROOT", "file:///tmp/test-warehouse")
    monkeypatch.setenv("SW_CATALOG", "test_catalog")
    monkeypatch.setenv("SW_VINTAGE", "2024")

    from socialwarehouse.orchestration.resources import WarehouseConfig

    cfg = WarehouseConfig()
    assert cfg.warehouse_root == "file:///tmp/test-warehouse"
    assert cfg.catalog == "test_catalog"
    assert cfg.vintage == 2024
    assert cfg.partition_state is None


def test_warehouse_config_explicit_overrides_env(monkeypatch):
    """Explicit kwargs override env defaults — instance projects rely on this."""
    monkeypatch.setenv("SW_WAREHOUSE_ROOT", "file:///env-default")

    from socialwarehouse.orchestration.resources import WarehouseConfig

    cfg = WarehouseConfig(warehouse_root="file:///explicit", catalog="uk_warehouse")
    assert cfg.warehouse_root == "file:///explicit"
    assert cfg.catalog == "uk_warehouse"


def test_spark_resource_constructs():
    """SparkResource accepts its declared config fields without opening a session."""
    from socialwarehouse.orchestration.resources import SparkResource

    r = SparkResource(app_name="test-app", enable_sedona=False)
    assert r.app_name == "test-app"
    assert r.enable_sedona is False


def test_postgis_resource_constructs():
    """PostGISResource accepts its declared config fields without opening a connection."""
    from socialwarehouse.orchestration.resources import PostGISResource

    r = PostGISResource(application_name="test", statement_timeout_ms=60_000)
    assert r.application_name == "test"
    assert r.statement_timeout_ms == 60_000
