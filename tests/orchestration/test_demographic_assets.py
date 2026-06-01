"""Topology tests for the demographic domain asset graph.

Verifies asset keys, dependency wiring, and registration in the
Definitions object — without executing compute functions (which
require Spark + a Delta cluster).

Skipped when ``dagster`` is not installed (the [orchestration] extra
is opt-in).
"""

from __future__ import annotations

import pytest

dagster = pytest.importorskip("dagster")
from dagster import AssetKey  # noqa: E402


class TestDemographicAssetKeys:

    def test_demographics_raw_source_asset(self):
        from socialwarehouse.orchestration.assets.demographic import demographics_raw

        assert demographics_raw.key == AssetKey(["warehouse", "bronze", "demographics_raw"])

    def test_demographics_typed_asset_key(self):
        from socialwarehouse.orchestration.assets.demographic import demographics_typed

        assert demographics_typed.key == AssetKey(["warehouse", "silver", "demographics_typed"])

    def test_demographics_enriched_asset_key(self):
        from socialwarehouse.orchestration.assets.demographic import demographics_enriched

        assert demographics_enriched.key == AssetKey(["warehouse", "gold", "demographics_enriched"])

    def test_fact_acs_estimate_postgis_key(self):
        from socialwarehouse.orchestration.assets.demographic import fact_acs_estimate_postgis

        assert fact_acs_estimate_postgis.key == AssetKey(["postgis", "sw_warehouse", "factacsestimate"])

    def test_fact_decennial_count_postgis_key(self):
        from socialwarehouse.orchestration.assets.demographic import fact_decennial_count_postgis

        assert fact_decennial_count_postgis.key == AssetKey(["postgis", "sw_warehouse", "factdecennialcount"])


class TestDemographicDependencyWiring:

    def test_demographics_typed_depends_on_raw(self):
        from socialwarehouse.orchestration.assets.demographic import demographics_typed

        assert AssetKey(["warehouse", "bronze", "demographics_raw"]) in demographics_typed.dependency_keys

    def test_demographics_enriched_depends_on_typed(self):
        from socialwarehouse.orchestration.assets.demographic import demographics_enriched

        assert AssetKey(["warehouse", "silver", "demographics_typed"]) in demographics_enriched.dependency_keys

    def test_acs_postgis_depends_on_enriched(self):
        from socialwarehouse.orchestration.assets.demographic import fact_acs_estimate_postgis

        assert AssetKey(["warehouse", "gold", "demographics_enriched"]) in fact_acs_estimate_postgis.dependency_keys

    def test_decennial_postgis_depends_on_enriched(self):
        from socialwarehouse.orchestration.assets.demographic import fact_decennial_count_postgis

        assert AssetKey(["warehouse", "gold", "demographics_enriched"]) in fact_decennial_count_postgis.dependency_keys


class TestDemographicRegistration:

    def test_all_assets_list_length(self):
        from socialwarehouse.orchestration.assets.demographic import all_assets

        assert len(all_assets) == 5

    def test_definitions_includes_demographic_assets(self):
        from socialwarehouse.orchestration import defs

        all_keys = {a.key for a in defs.assets if isinstance(a, dagster.AssetsDefinition)}
        assert AssetKey(["warehouse", "silver", "demographics_typed"]) in all_keys
        assert AssetKey(["warehouse", "gold", "demographics_enriched"]) in all_keys
        assert AssetKey(["postgis", "sw_warehouse", "factacsestimate"]) in all_keys
        assert AssetKey(["postgis", "sw_warehouse", "factdecennialcount"]) in all_keys
