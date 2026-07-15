"""Tests for the Census vintage partition infrastructure (SW#281).

Verifies partition key parsing, hot/cold tier policy, and that the
factories correctly accept partitions_def without breaking
non-partitioned usage.

Skipped when ``dagster`` is not installed.
"""

from __future__ import annotations

import pytest

dagster = pytest.importorskip("dagster")
from dagster import AssetKey, StaticPartitionsDefinition  # noqa: E402


class TestParseVintagePartition:
    def test_acs5_partition(self):
        from socialwarehouse.orchestration.partitions import parse_vintage_partition

        p = parse_vintage_partition("acs5_2022")
        assert p.survey_type == "acs5"
        assert p.vintage_year == 2022
        assert p.end_year == 2022

    def test_decennial_partition(self):
        from socialwarehouse.orchestration.partitions import parse_vintage_partition

        p = parse_vintage_partition("dec_2010")
        assert p.survey_type == "dec"
        assert p.vintage_year == 2010

    def test_invalid_format_raises(self):
        from socialwarehouse.orchestration.partitions import parse_vintage_partition

        with pytest.raises(ValueError, match="Invalid vintage partition key"):
            parse_vintage_partition("bad")

    def test_unknown_survey_type_raises(self):
        from socialwarehouse.orchestration.partitions import parse_vintage_partition

        with pytest.raises(ValueError, match="Unknown survey type"):
            parse_vintage_partition("sf1_2010")

    def test_non_integer_year_raises(self):
        from socialwarehouse.orchestration.partitions import parse_vintage_partition

        with pytest.raises(ValueError, match="Non-integer year"):
            parse_vintage_partition("acs5_abcd")


class TestIsHotVintage:
    def test_current_vintage_is_hot(self):
        from socialwarehouse.orchestration.partitions import is_hot_vintage

        assert is_hot_vintage(2022, current_vintage=2022, hot_window_count=1) is True

    def test_old_vintage_is_cold(self):
        from socialwarehouse.orchestration.partitions import is_hot_vintage

        assert is_hot_vintage(2010, current_vintage=2022, hot_window_count=1) is False

    def test_expanded_window(self):
        from socialwarehouse.orchestration.partitions import is_hot_vintage

        assert is_hot_vintage(2021, current_vintage=2022, hot_window_count=2) is True
        assert is_hot_vintage(2020, current_vintage=2022, hot_window_count=2) is False

    def test_zero_window_is_all_cold(self):
        from socialwarehouse.orchestration.partitions import is_hot_vintage

        assert is_hot_vintage(2022, current_vintage=2022, hot_window_count=0) is False


class TestPartitionDefinition:
    def test_partition_keys_exist(self):
        from socialwarehouse.orchestration.partitions import CENSUS_VINTAGE_PARTITIONS

        assert isinstance(CENSUS_VINTAGE_PARTITIONS, StaticPartitionsDefinition)
        keys = CENSUS_VINTAGE_PARTITIONS.get_partition_keys()
        assert "dec_2020" in keys
        assert "dec_2010" in keys
        assert "acs5_2022" in keys
        assert "acs5_2009" in keys

    def test_all_keys_parseable(self):
        from socialwarehouse.orchestration.partitions import (
            CENSUS_VINTAGE_PARTITIONS,
            parse_vintage_partition,
        )

        for key in CENSUS_VINTAGE_PARTITIONS.get_partition_keys():
            p = parse_vintage_partition(key)
            assert p.survey_type in ("acs5", "dec")
            assert isinstance(p.vintage_year, int)


class TestFactoriesWithPartitions:
    def test_delta_table_asset_with_partitions(self):
        from socialwarehouse.orchestration.asset_factories import delta_table_asset
        from socialwarehouse.orchestration.partitions import CENSUS_VINTAGE_PARTITIONS

        def _noop(context, spark):
            pass

        a = delta_table_asset(
            layer="gold",
            table="partitioned_table",
            deps=["silver/source"],
            compute_fn=_noop,
            partitions_def=CENSUS_VINTAGE_PARTITIONS,
        )
        assert isinstance(a, dagster.AssetsDefinition)
        assert a.partitions_def is CENSUS_VINTAGE_PARTITIONS
        assert a.key == AssetKey(["warehouse", "gold", "partitioned_table"])

    def test_delta_table_asset_without_partitions_unchanged(self):
        from socialwarehouse.orchestration.asset_factories import delta_table_asset

        def _noop(context, spark):
            pass

        a = delta_table_asset(
            layer="silver",
            table="non_partitioned",
            compute_fn=_noop,
        )
        assert a.partitions_def is None

    def test_postgis_asset_with_partitions(self):
        from socialwarehouse.orchestration.asset_factories import postgis_materialization_asset
        from socialwarehouse.orchestration.partitions import CENSUS_VINTAGE_PARTITIONS

        def _noop(spark, path):
            pass

        a = postgis_materialization_asset(
            source_layer="gold",
            source_table="enriched",
            target_django_app_label="geo",
            target_django_model_name="Thing",
            compute_sql=_noop,
            partitions_def=CENSUS_VINTAGE_PARTITIONS,
        )
        assert a.partitions_def is CENSUS_VINTAGE_PARTITIONS

    def test_postgis_asset_without_partitions_unchanged(self):
        from socialwarehouse.orchestration.asset_factories import postgis_materialization_asset

        def _noop(spark, path):
            pass

        a = postgis_materialization_asset(
            source_layer="gold",
            source_table="enriched",
            target_django_app_label="geo",
            target_django_model_name="Thing",
            compute_sql=_noop,
        )
        assert a.partitions_def is None


class TestGeoAssetsPartitioned:
    def test_addresses_enriched_is_partitioned(self):
        from socialwarehouse.orchestration.assets.geo import addresses_enriched
        from socialwarehouse.orchestration.partitions import CENSUS_VINTAGE_PARTITIONS

        assert addresses_enriched.partitions_def is CENSUS_VINTAGE_PARTITIONS

    def test_geo_address_postgis_is_partitioned(self):
        from socialwarehouse.orchestration.assets.geo import geo_address_postgis
        from socialwarehouse.orchestration.partitions import CENSUS_VINTAGE_PARTITIONS

        assert geo_address_postgis.partitions_def is CENSUS_VINTAGE_PARTITIONS

    def test_addresses_typed_is_not_partitioned(self):
        from socialwarehouse.orchestration.assets.geo import addresses_typed

        assert addresses_typed.partitions_def is None


class TestWarehouseConfigHotWindow:
    def test_default_hot_window(self):
        from socialwarehouse.orchestration.resources import WarehouseConfig

        config = WarehouseConfig()
        assert config.hot_window_count == 1

    def test_custom_hot_window(self):
        from socialwarehouse.orchestration.resources import WarehouseConfig

        config = WarehouseConfig(hot_window_count=3)
        assert config.hot_window_count == 3


class TestBackfillJobRegistered:
    def test_backfill_job_in_definitions(self):
        from socialwarehouse.orchestration.schedules import geo_vintage_backfill_job

        assert geo_vintage_backfill_job is not None
        assert geo_vintage_backfill_job.name == "geo_vintage_backfill"

    def test_definitions_still_load(self):
        from socialwarehouse.orchestration.definitions import defs

        assert isinstance(defs, dagster.Definitions)
        all_keys = {a.key for a in defs.assets if isinstance(a, dagster.AssetsDefinition)}
        assert AssetKey(["warehouse", "gold", "addresses_enriched"]) in all_keys
