"""
Tests for SW#261: Silver Delta -> PostGIS materialization.

Pure-Python tests cover vendor-extras dispatch + chunking + FK lookup
construction. Django-DB-required tests cover the bulk_create upsert
path against the actual DimPerson model. PySpark + Django-DB tests
cover the end-to-end materialize_all against the existing TS fixtures.
"""

from datetime import date, datetime, timezone

import pytest


class TestVendorExtrasDispatch:
    """`_silver_persons_to_dimperson_kwargs` vendor dispatch — pure Python."""

    def _row(self, **overrides):
        row = {
            "vendor": "ts",
            "vendor_voter_id": "TS001",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "registration_state": "TX",
            "registration_status": "active",
            "vendor_extras": {"vb.tsmart_partisan_score": "72"},
        }
        row.update(overrides)
        return row

    def test_ts_vendor_routes_to_ts_extras(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row())
        assert out["ts_extras"] == {"vb.tsmart_partisan_score": "72"}
        assert out["pdi_extras"] == {}
        assert out["l2_extras"] == {}
        assert out["catalist_extras"] == {}

    def test_l2_vendor_routes_to_l2_extras(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row(
            vendor="l2", vendor_extras={"LALVOTERID": "L-99"}
        ))
        assert out["l2_extras"] == {"LALVOTERID": "L-99"}
        assert out["ts_extras"] == {}

    def test_pdi_vendor_routes_to_pdi_extras(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row(
            vendor="pdi", vendor_extras={"pdi_internal_id": "P-1"}
        ))
        assert out["pdi_extras"] == {"pdi_internal_id": "P-1"}

    def test_unknown_vendor_drops_extras(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row(vendor="unknown_vendor"))
        # All four extras fields default to {} (extras content dropped).
        assert out["ts_extras"] == {}
        assert out["l2_extras"] == {}
        assert out["pdi_extras"] == {}
        assert out["catalist_extras"] == {}

    def test_canonical_fields_pass_through(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row())
        assert out["first_name"] == "Ada"
        assert out["last_name"] == "Lovelace"
        assert out["registration_state"] == "TX"
        assert out["registration_status"] == "active"
        assert out["vendor"] == "ts"
        assert out["vendor_voter_id"] == "TS001"

    def test_vendor_state_mirrors_registration_state(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row())
        assert out["vendor_state"] == "TX"

    def test_missing_optional_fields_default_safely(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        row = {
            "vendor": "ts",
            "vendor_voter_id": "TS001",
            "registration_state": "TX",
        }
        out = _silver_persons_to_dimperson_kwargs(row)
        assert out["first_name"] == ""
        assert out["registration_status"] == "not_registered"
        assert out["general_election_count"] == 0

    def test_ontology_mixin_fields_populated(self):
        from socialwarehouse.core.mixins import generate_entity_uuid5
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row())
        assert out["data_source"] == "ts"
        assert out["jurisdiction_level"] == "state"
        assert out["jurisdiction_state"] == "TX"
        assert out["source_record_id"] == "TS001"
        assert out["entity_uuid"] == generate_entity_uuid5("ts", "TS001")

    def test_entity_uuid_deterministic_across_calls(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out1 = _silver_persons_to_dimperson_kwargs(self._row())
        out2 = _silver_persons_to_dimperson_kwargs(self._row())
        assert out1["entity_uuid"] == out2["entity_uuid"]

    def test_entity_uuid_differs_by_vendor(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out_ts = _silver_persons_to_dimperson_kwargs(self._row(vendor="ts"))
        out_l2 = _silver_persons_to_dimperson_kwargs(self._row(vendor="l2"))
        assert out_ts["entity_uuid"] != out_l2["entity_uuid"]

    def test_data_source_falls_back_to_vendor(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row())
        assert out["data_source"] == "ts"

    def test_data_source_prefers_explicit(self):
        from swh.voters.materialize import _silver_persons_to_dimperson_kwargs
        out = _silver_persons_to_dimperson_kwargs(self._row(data_source="targetsmart"))
        assert out["data_source"] == "targetsmart"


class TestChunking:
    def test_chunk_smaller_than_size(self):
        from swh.voters.materialize import _chunked
        result = list(_chunked([1, 2, 3], 10))
        assert result == [[1, 2, 3]]

    def test_chunk_exact_multiple(self):
        from swh.voters.materialize import _chunked
        result = list(_chunked([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_chunk_with_remainder(self):
        from swh.voters.materialize import _chunked
        result = list(_chunked([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_chunk_empty(self):
        from swh.voters.materialize import _chunked
        assert list(_chunked([], 10)) == []


@pytest.mark.django_db
class TestIdLookup:
    def test_lookup_returns_id_for_matched_natural_key(self):
        from socialwarehouse.warehouse.models import DimPerson
        from swh.voters.materialize import _build_id_lookup

        p = DimPerson.objects.create(
            vendor="ts", vendor_voter_id="LOOKUP-1",
            registration_state="TX", registration_status="active",
        )
        lookup = _build_id_lookup({"ts:LOOKUP-1"})
        assert lookup == {("ts", "LOOKUP-1"): p.id}

    def test_lookup_missing_returns_empty(self):
        from swh.voters.materialize import _build_id_lookup
        lookup = _build_id_lookup({"ts:NONEXISTENT"})
        assert lookup == {}

    def test_lookup_mixed_vendors(self):
        from socialwarehouse.warehouse.models import DimPerson
        from swh.voters.materialize import _build_id_lookup

        ts_p = DimPerson.objects.create(
            vendor="ts", vendor_voter_id="X",
            registration_state="TX", registration_status="active",
        )
        l2_p = DimPerson.objects.create(
            vendor="l2", vendor_voter_id="X",
            registration_state="TX", registration_status="active",
        )
        lookup = _build_id_lookup({"ts:X", "l2:X"})
        assert lookup[("ts", "X")] == ts_p.id
        assert lookup[("l2", "X")] == l2_p.id

    def test_lookup_handles_empty_input(self):
        from swh.voters.materialize import _build_id_lookup
        assert _build_id_lookup(set()) == {}

    def test_lookup_skips_malformed_keys(self):
        from swh.voters.materialize import _build_id_lookup
        # Keys without ":" separator skipped.
        assert _build_id_lookup({"no-colon", "also-no-colon"}) == {}


# Spark + Django-DB end-to-end tests
pyspark = pytest.importorskip("pyspark", reason="pyspark not installed; end-to-end materialization tests skipped")


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    import os
    warehouse_root = tmp_path_factory.mktemp("warehouse-materialize")
    os.environ["SW_WAREHOUSE_ROOT"] = f"file://{warehouse_root}"

    from pyspark.sql import SparkSession
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("sw261-materialize-test")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.mark.django_db(transaction=True)
class TestMaterializeEndToEnd:
    def test_materialize_all_from_ts_fixtures(self, spark):
        from pathlib import Path

        from socialwarehouse.warehouse.models import (
            DimPerson, FactPersonScore, FactVoteHistory,
        )
        from swh.voters.materialize import materialize_all
        from swh.voters.ts.bronze import ingest_bronze
        from swh.voters.ts.scores import extract_scores
        from swh.voters.ts.silver import build_silver_persons
        from swh.voters.ts.vote_history import compute_aggregates, extract_vote_history

        fixtures = Path(__file__).resolve().parents[3] / "fixtures"

        # Ingest both TS fixtures: 10-row sample + 4-row history fixture.
        ingest_bronze(spark, csv_path=fixtures / "ts_sample.csv", state="TX")
        ingest_bronze(spark, csv_path=fixtures / "ts_with_history.csv", state="TX")
        build_silver_persons(spark)
        extract_scores(spark)
        extract_vote_history(spark)
        compute_aggregates(spark)

        counts = materialize_all(spark)

        # 10 + 4 = 14 distinct natural-key persons.
        assert counts["persons"] == 14
        assert DimPerson.objects.count() == 14
        # 10 fixture persons * 2 scores each = 20.
        assert counts["scores"] == 20
        assert FactPersonScore.objects.count() == 20
        # SV001 (6 events) + RV001 (3) + OV001 (1) = 10.
        assert counts["vote_history"] == 10
        assert FactVoteHistory.objects.count() == 10

    def test_materialize_is_idempotent(self, spark):
        from socialwarehouse.warehouse.models import (
            DimPerson, FactPersonScore, FactVoteHistory,
        )
        from swh.voters.materialize import materialize_all

        # Run again — same end-state.
        counts = materialize_all(spark)
        assert counts["persons"] == 14
        assert DimPerson.objects.count() == 14
        assert FactPersonScore.objects.count() == 20
        assert FactVoteHistory.objects.count() == 10

    def test_vendor_extras_landed_on_ts_extras(self, spark):
        from socialwarehouse.warehouse.models import DimPerson

        ada = DimPerson.objects.get(vendor="ts", vendor_voter_id="TS001")
        # vb.tsmart_made_up_field_a is unmapped in TS_TO_CANONICAL → stashed in extras.
        assert "vb.tsmart_made_up_field_a" in ada.ts_extras
        # Other vendor extras remain empty.
        assert ada.l2_extras == {}
        assert ada.pdi_extras == {}
        assert ada.catalist_extras == {}

    def test_aggregates_materialized_for_super_voter(self, spark):
        from socialwarehouse.warehouse.models import DimPerson

        sv = DimPerson.objects.get(vendor="ts", vendor_voter_id="SV001")
        assert sv.general_election_count == 4
        assert sv.vote_frequency_category == "super_voter"
        assert sv.last_voted_at == date(2024, 11, 5)

    def test_ts_materializer_writes_after_migration(self, spark):
        """Named test per #286 Step 3: verify materializer populates mixin fields."""
        from socialwarehouse.core.mixins import generate_entity_uuid5
        from socialwarehouse.warehouse.models import DimPerson

        ada = DimPerson.objects.get(vendor="ts", vendor_voter_id="TS001")
        assert ada.entity_uuid == generate_entity_uuid5("ts", "TS001")
        assert ada.data_source == "ts"
        assert ada.jurisdiction_level == "state"
        assert ada.jurisdiction_state == "TX"
        assert ada.source_record_id == "TS001"
