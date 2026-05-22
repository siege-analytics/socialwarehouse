"""
Tests for SW#257: TargetSmart importer thin spine (bronze + silver.persons).

Per writing-tests:1, each test fails on revert. PySpark-required tests
are gated by importorskip; the mapping-table tests run without Spark.
"""

from pathlib import Path

import pytest


FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "ts_sample.csv"


class TestMappings:
    """Pure-Python mapping tests — no Spark required."""

    def test_natural_key_field_present(self):
        from swh.voters.ts.bronze import TS_VOTER_ID_COLUMN
        assert TS_VOTER_ID_COLUMN == "vb.voterbase_id"

    def test_canonical_targets_include_required_fields(self):
        from swh.voters.ts.mappings import CANONICAL_FIELDS
        required = {"first_name", "last_name", "registration_state",
                    "vendor_address_line1", "latitude", "longitude"}
        assert required <= CANONICAL_FIELDS

    def test_mapping_strips_tsmart_prefix(self):
        from swh.voters.ts.mappings import TS_TO_CANONICAL
        assert TS_TO_CANONICAL["vb.tsmart_first_name"] == "first_name"
        assert TS_TO_CANONICAL["vb.tsmart_household_id"] == "household_id"

    def test_pii_field_explicitly_excluded(self):
        from swh.voters.ts.mappings import TS_TO_CANONICAL
        # vb.voterbase_phone_wireless mapped to None means "excluded
        # from canonical AND from extras"; opt-in only.
        assert "vb.voterbase_phone_wireless" in TS_TO_CANONICAL
        assert TS_TO_CANONICAL["vb.voterbase_phone_wireless"] is None


class TestSilverMapper:
    """Tests for the in-memory map_raw_to_canonical helper (no Spark)."""

    def _sample_raw(self):
        return {
            "vb.voterbase_id": "TS001",
            "vb.tsmart_first_name": "Ada",
            "vb.tsmart_last_name": "Lovelace",
            "vb.voterbase_dob": "1985-12-10",
            "vb.vf_voter_status": "active",
            "vb.vf_source_state": "TX",
            "vb.tsmart_latitude": "30.2672",
            "vb.tsmart_longitude": "-97.7431",
            "vb.tsmart_household_size": "2",
            "vb.tsmart_is_head_of_household": "t",
            "vb.tsmart_partisan_score": "72",  # unmapped -> extras
            "vb.tsmart_made_up_field_a": "foo",  # unmapped -> extras
            "vb.voterbase_phone_wireless": "+15125550100",  # excluded entirely
        }

    def test_canonical_fields_mapped(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        assert out["first_name"] == "Ada"
        assert out["last_name"] == "Lovelace"
        assert out["registration_status"] == "active"
        assert out["registration_state"] == "TX"

    def test_lat_lon_coerced_to_float(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        assert isinstance(out["latitude"], float)
        assert out["latitude"] == pytest.approx(30.2672)
        assert isinstance(out["longitude"], float)

    def test_household_size_coerced_to_int(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        assert out["household_size"] == 2

    def test_is_head_of_household_coerced_to_bool(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        assert out["is_head_of_household"] is True

    def test_unmapped_fields_go_to_vendor_extras(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        assert "vb.tsmart_partisan_score" in out["vendor_extras"]
        assert out["vendor_extras"]["vb.tsmart_partisan_score"] == "72"
        assert "vb.tsmart_made_up_field_a" in out["vendor_extras"]
        assert out["vendor_extras"]["vb.tsmart_made_up_field_a"] == "foo"

    def test_explicit_excluded_field_not_in_extras(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        # vb.voterbase_phone_wireless was mapped to None -> exclude entirely
        assert "vb.voterbase_phone_wireless" not in out["vendor_extras"]

    def test_natural_key_not_in_canonical_dict(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        # vendor_voter_id is supplied by the caller, not the mapper
        assert "vendor_voter_id" not in out

    def test_registration_state_falls_back_to_default_when_missing(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        raw = self._sample_raw()
        raw["vb.vf_source_state"] = ""
        out = _map_raw_to_canonical(raw, "CA")
        assert out["registration_state"] == "CA"

    def test_vendor_state_mirrors_registration_state(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        out = _map_raw_to_canonical(self._sample_raw(), "TX")
        assert out["vendor_state"] == "TX"

    def test_empty_value_coerces_to_none(self):
        from swh.voters.ts.silver import _map_raw_to_canonical
        raw = self._sample_raw()
        raw["vb.tsmart_latitude"] = ""
        out = _map_raw_to_canonical(raw, "TX")
        assert out["latitude"] is None


class TestFixture:
    """Sanity tests on the fixture itself — independent of Spark."""

    def test_fixture_exists(self):
        assert FIXTURE.is_file(), f"Fixture not found at {FIXTURE}"

    def test_fixture_has_ten_rows(self):
        with open(FIXTURE, encoding="utf-8") as f:
            n = sum(1 for _ in f) - 1  # subtract header
        assert n == 10

    def test_fixture_has_natural_key_column(self):
        with open(FIXTURE, encoding="utf-8") as f:
            header = f.readline().rstrip()
        assert "vb.voterbase_id" in header

    def test_fixture_has_unmapped_fields_for_extras_coverage(self):
        """Fixture must include columns NOT in TS_TO_CANONICAL so the
        silver build's extras-stash path is exercised."""
        from swh.voters.ts.mappings import TS_TO_CANONICAL
        with open(FIXTURE, encoding="utf-8") as f:
            header = f.readline().rstrip().split(",")
        unmapped = [c for c in header if c not in TS_TO_CANONICAL and c != "vb.voterbase_id"]
        assert len(unmapped) >= 2, f"Fixture lacks unmapped fields; got header {header}"


# PySpark-dependent end-to-end tests. Gated so CI Test-suite job (no
# pyspark) skips; docker-build job (with pyspark) runs them.
pyspark = pytest.importorskip("pyspark", reason="pyspark not installed; bronze/silver end-to-end tests skipped")


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    """Local-only Spark session pointed at a temp warehouse root.

    This bypasses the s3a:// path validation in delta/config.py by
    setting SW_WAREHOUSE_ROOT to a file:// path before importing the
    delta module.
    """
    import os
    warehouse_root = tmp_path_factory.mktemp("warehouse")
    os.environ["SW_WAREHOUSE_ROOT"] = f"file://{warehouse_root}"

    from pyspark.sql import SparkSession
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("sw257-ts-importer-test")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


class TestBronzeIngest:
    def test_ingest_fixture(self, spark):
        from swh.voters.ts.bronze import ingest_bronze
        n = ingest_bronze(spark, csv_path=FIXTURE, state="TX")
        assert n == 10

    def test_bronze_appends_on_reload(self, spark):
        from swh.voters.ts.bronze import ingest_bronze
        n2 = ingest_bronze(spark, csv_path=FIXTURE, state="TX")
        assert n2 == 10  # 10 more appended


class TestSilverBuild:
    def test_build_silver_persons_dedupes_to_distinct_voter_ids(self, spark):
        from socialwarehouse.delta.tables import TABLES
        from swh.voters.ts.silver import build_silver_persons
        # After TestBronzeIngest's two appends, bronze has 20 rows but only
        # 10 distinct natural keys. Silver should land at 10.
        n_silver = build_silver_persons(spark)
        assert n_silver == 10
        # Re-running is idempotent
        n_silver_again = build_silver_persons(spark)
        assert n_silver_again == 10

    def test_silver_has_canonical_fields(self, spark):
        from socialwarehouse.delta.tables import TABLES
        df = spark.read.format("delta").load(TABLES["silver.persons"]["path"])
        ada = df.filter(df.vendor_voter_id == "TS001").collect()[0]
        assert ada.first_name == "Ada"
        assert ada.last_name == "Lovelace"
        assert ada.registration_state == "TX"
        assert ada.vendor == "ts"

    def test_silver_stashes_unmapped_in_extras(self, spark):
        from socialwarehouse.delta.tables import TABLES
        df = spark.read.format("delta").load(TABLES["silver.persons"]["path"])
        ada = df.filter(df.vendor_voter_id == "TS001").collect()[0]
        extras = ada.vendor_extras
        assert "vb.tsmart_partisan_score" in extras
        assert extras["vb.tsmart_partisan_score"] == "72"
