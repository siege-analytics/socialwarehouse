"""Topology tests for the civic domain asset graph.

Verifies asset keys + dependency keys are wired correctly without
executing compute functions (which would need Spark + Delta).

Skipped when ``dagster`` is not installed (the [orchestration] extra
is opt-in).
"""

from __future__ import annotations

import pytest

dagster = pytest.importorskip("dagster")
from dagster import AssetKey  # noqa: E402


class TestCivicSourceAssets:
    """Bronze SourceAssets have the expected keys and group."""

    def test_nces_districts_raw_key(self):
        from socialwarehouse.orchestration.assets.civic import nces_districts_raw

        assert nces_districts_raw.key == AssetKey(["warehouse", "bronze", "nces_districts_raw"])

    def test_nces_schools_raw_key(self):
        from socialwarehouse.orchestration.assets.civic import nces_schools_raw

        assert nces_schools_raw.key == AssetKey(["warehouse", "bronze", "nces_schools_raw"])

    def test_nces_edge_raw_key(self):
        from socialwarehouse.orchestration.assets.civic import nces_edge_raw

        assert nces_edge_raw.key == AssetKey(["warehouse", "bronze", "nces_edge_raw"])


class TestCivicSilverAssets:
    """Silver delta_table_assets have correct keys and upstream deps."""

    def test_nces_districts_typed_key_and_deps(self):
        from socialwarehouse.orchestration.assets.civic import nces_districts_typed

        assert nces_districts_typed.key == AssetKey(["warehouse", "silver", "nces_districts_typed"])
        assert AssetKey(["warehouse", "bronze", "nces_districts_raw"]) in nces_districts_typed.dependency_keys

    def test_nces_schools_typed_key_and_deps(self):
        from socialwarehouse.orchestration.assets.civic import nces_schools_typed

        assert nces_schools_typed.key == AssetKey(["warehouse", "silver", "nces_schools_typed"])
        assert AssetKey(["warehouse", "bronze", "nces_schools_raw"]) in nces_schools_typed.dependency_keys

    def test_nces_edge_typed_key_and_deps(self):
        from socialwarehouse.orchestration.assets.civic import nces_edge_typed

        assert nces_edge_typed.key == AssetKey(["warehouse", "silver", "nces_edge_typed"])
        assert AssetKey(["warehouse", "bronze", "nces_edge_raw"]) in nces_edge_typed.dependency_keys


class TestCivicPostgisAssets:
    """PostGIS materialization assets have correct keys and upstream deps."""

    def test_civic_district_postgis_key_and_deps(self):
        from socialwarehouse.orchestration.assets.civic import civic_district_postgis

        assert civic_district_postgis.key == AssetKey(["postgis", "sw_civic", "ncesdistrictaggregate"])
        assert AssetKey(["warehouse", "silver", "nces_districts_typed"]) in civic_district_postgis.dependency_keys

    def test_civic_school_postgis_key_and_deps(self):
        from socialwarehouse.orchestration.assets.civic import civic_school_postgis

        assert civic_school_postgis.key == AssetKey(["postgis", "sw_civic", "ncesschoolaggregate"])
        assert AssetKey(["warehouse", "silver", "nces_schools_typed"]) in civic_school_postgis.dependency_keys

    def test_civic_edge_postgis_key_and_deps(self):
        from socialwarehouse.orchestration.assets.civic import civic_edge_postgis

        assert civic_edge_postgis.key == AssetKey(["postgis", "sw_civic", "ncesdistrictedgedemographics"])
        assert AssetKey(["warehouse", "silver", "nces_edge_typed"]) in civic_edge_postgis.dependency_keys


class TestCivicAllAssets:
    """The all_assets list is complete and correctly ordered."""

    def test_all_assets_count(self):
        from socialwarehouse.orchestration.assets.civic import all_assets

        assert len(all_assets) == 9

    def test_all_assets_contains_all_chains(self):
        from socialwarehouse.orchestration.assets.civic import (
            all_assets,
            civic_district_postgis,
            civic_edge_postgis,
            civic_school_postgis,
            nces_districts_raw,
            nces_districts_typed,
            nces_edge_raw,
            nces_edge_typed,
            nces_schools_raw,
            nces_schools_typed,
        )

        expected = {
            nces_districts_raw,
            nces_districts_typed,
            civic_district_postgis,
            nces_schools_raw,
            nces_schools_typed,
            civic_school_postgis,
            nces_edge_raw,
            nces_edge_typed,
            civic_edge_postgis,
        }
        assert set(all_assets) == expected
