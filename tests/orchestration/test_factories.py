"""Sanity tests for the orchestration asset factories.

Verifies the factories produce AssetsDefinition objects with the
expected asset keys + dep keys, without actually executing the
compute functions (which would need Spark + a Delta cluster).

Skipped when ``dagster`` is not installed (the [orchestration] extra
is opt-in).
"""

from __future__ import annotations

import pytest

dagster = pytest.importorskip("dagster")
from dagster import AssetKey  # noqa: E402


def test_delta_table_asset_factory_produces_assets_definition():
    """delta_table_asset returns an AssetsDefinition with the expected key + deps."""
    from socialwarehouse.orchestration.asset_factories import delta_table_asset

    def _noop(context, spark):
        pass

    a = delta_table_asset(
        layer="silver",
        table="my_table",
        deps=["bronze/source_table"],
        compute_fn=_noop,
    )
    assert isinstance(a, dagster.AssetsDefinition)
    assert a.key == AssetKey(["warehouse", "silver", "my_table"])
    assert AssetKey(["warehouse", "bronze", "source_table"]) in a.dependency_keys


def test_delta_table_asset_factory_no_deps():
    """delta_table_asset works for assets with no upstream deps (e.g. raw bronze)."""
    from socialwarehouse.orchestration.asset_factories import delta_table_asset

    def _noop(context, spark):
        pass

    a = delta_table_asset(
        layer="bronze",
        table="standalone",
        compute_fn=_noop,
    )
    assert a.key == AssetKey(["warehouse", "bronze", "standalone"])
    assert len(a.dependency_keys) == 0


def test_postgis_materialization_factory_produces_assets_definition():
    """postgis_materialization_asset returns AssetsDefinition with the postgis key prefix."""
    from socialwarehouse.orchestration.asset_factories import postgis_materialization_asset

    def _noop(spark, source_path):
        pass

    a = postgis_materialization_asset(
        source_layer="gold",
        source_table="my_gold",
        target_django_app_label="geo",
        target_django_model_name="Thing",
        compute_sql=_noop,
    )
    assert isinstance(a, dagster.AssetsDefinition)
    assert a.key == AssetKey(["postgis", "geo", "thing"])
    assert AssetKey(["warehouse", "gold", "my_gold"]) in a.dependency_keys


def test_definitions_object_loads():
    """The Definitions object at socialwarehouse.orchestration.defs loads without raising."""
    from socialwarehouse.orchestration import defs

    assert isinstance(defs, dagster.Definitions)
    # geo assets registered:
    all_keys = {a.key for a in defs.assets if isinstance(a, dagster.AssetsDefinition)}
    assert AssetKey(["warehouse", "silver", "addresses_typed"]) in all_keys
    assert AssetKey(["warehouse", "gold", "addresses_enriched"]) in all_keys
    assert AssetKey(["postgis", "geo", "address"]) in all_keys
