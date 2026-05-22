"""
Tests for SW#260: TargetSmart vote-history extraction + Person aggregates.

Pure-Python tests cover column-pattern parsing, method-code mapping,
truthiness, and frequency bucketing. Spark-gated tests cover the
end-to-end extract + aggregate against the dedicated history fixture.
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest


class TestColumnParsing:
    def test_general_year(self):
        from swh.voters.ts.vote_history_mappings import parse_column
        assert parse_column("vb.vf_g_2024") == ("general", 2024, False)

    def test_primary_year(self):
        from swh.voters.ts.vote_history_mappings import parse_column
        assert parse_column("vb.vf_p_2022") == ("primary", 2022, False)

    def test_general_method(self):
        from swh.voters.ts.vote_history_mappings import parse_column
        assert parse_column("vb.vf_g_method_2024") == ("general", 2024, True)

    def test_primary_method(self):
        from swh.voters.ts.vote_history_mappings import parse_column
        assert parse_column("vb.vf_p_method_2020") == ("primary", 2020, True)

    def test_non_vote_history_returns_none(self):
        from swh.voters.ts.vote_history_mappings import parse_column
        assert parse_column("vb.tsmart_first_name") is None
        assert parse_column("vb.vf_party") is None

    def test_non_year_suffix_returns_none(self):
        from swh.voters.ts.vote_history_mappings import parse_column
        assert parse_column("vb.vf_g_foo") is None


class TestMethodCodes:
    def test_in_person(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("I") == "in_person"

    def test_absentee(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("A") == "absentee"

    def test_mail(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("M") == "mail"

    def test_early(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("E") == "early"

    def test_provisional(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("P") == "provisional"

    def test_empty_is_unknown(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("") == "unknown"

    def test_unknown_code_falls_back_to_unknown(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method("Z") == "unknown"

    def test_none_is_unknown(self):
        from swh.voters.ts.vote_history_mappings import canonical_method
        assert canonical_method(None) == "unknown"


class TestTruthiness:
    def test_y_is_voted(self):
        from swh.voters.ts.vote_history_mappings import is_voted
        assert is_voted("Y") is True
        assert is_voted("y") is True

    def test_one_is_voted(self):
        from swh.voters.ts.vote_history_mappings import is_voted
        assert is_voted("1") is True

    def test_n_is_not_voted(self):
        from swh.voters.ts.vote_history_mappings import is_voted
        assert is_voted("N") is False
        assert is_voted("0") is False
        assert is_voted("") is False
        assert is_voted(None) is False


class TestElectionDate:
    def test_general_date(self):
        from swh.voters.ts.vote_history_mappings import election_date_for
        assert election_date_for("general", 2024) == date(2024, 11, 5)

    def test_primary_date(self):
        from swh.voters.ts.vote_history_mappings import election_date_for
        assert election_date_for("primary", 2022) == date(2022, 3, 15)


class TestFrequencyCategory:
    def test_super_voter(self):
        from swh.voters.ts.vote_history_mappings import vote_frequency_category
        assert vote_frequency_category(general_count=4, total_count=5) == "super_voter"
        assert vote_frequency_category(general_count=5, total_count=5) == "super_voter"

    def test_regular(self):
        from swh.voters.ts.vote_history_mappings import vote_frequency_category
        assert vote_frequency_category(2, 4) == "regular"
        assert vote_frequency_category(3, 5) == "regular"

    def test_occasional(self):
        from swh.voters.ts.vote_history_mappings import vote_frequency_category
        assert vote_frequency_category(1, 1) == "occasional"

    def test_non(self):
        from swh.voters.ts.vote_history_mappings import vote_frequency_category
        assert vote_frequency_category(0, 0) == "non"
        # Even if voter has primary participation but no generals, they're "non"
        assert vote_frequency_category(0, 3) == "non"


class TestRowEmission:
    def _now(self):
        return datetime(2026, 5, 22, tzinfo=timezone.utc)

    def test_voted_general_with_method(self):
        from swh.voters.ts.vote_history import _vote_history_rows_from_raw
        raw = {
            "vb.vf_g_2024": "Y",
            "vb.vf_g_method_2024": "I",
        }
        rows = _vote_history_rows_from_raw(raw, "ts:X", self._now())
        assert len(rows) == 1
        assert rows[0]["election_type"] == "general"
        assert rows[0]["election_year"] == 2024
        assert rows[0]["election_date"] == date(2024, 11, 5)
        assert rows[0]["voted_method"] == "in_person"

    def test_voted_no_method_falls_back_to_unknown(self):
        from swh.voters.ts.vote_history import _vote_history_rows_from_raw
        raw = {"vb.vf_g_2024": "Y"}
        rows = _vote_history_rows_from_raw(raw, "ts:X", self._now())
        assert len(rows) == 1
        assert rows[0]["voted_method"] == "unknown"

    def test_not_voted_emits_nothing(self):
        from swh.voters.ts.vote_history import _vote_history_rows_from_raw
        raw = {"vb.vf_g_2024": "N", "vb.vf_g_method_2024": ""}
        rows = _vote_history_rows_from_raw(raw, "ts:X", self._now())
        assert rows == []

    def test_method_without_participation_emits_nothing(self):
        from swh.voters.ts.vote_history import _vote_history_rows_from_raw
        # Method column present but no Y for the corresponding year.
        raw = {"vb.vf_g_method_2024": "I"}
        rows = _vote_history_rows_from_raw(raw, "ts:X", self._now())
        assert rows == []

    def test_multiple_cycles(self):
        from swh.voters.ts.vote_history import _vote_history_rows_from_raw
        raw = {
            "vb.vf_g_2024": "Y", "vb.vf_g_method_2024": "I",
            "vb.vf_g_2022": "Y", "vb.vf_g_method_2022": "M",
            "vb.vf_p_2024": "Y",  # no method = unknown
        }
        rows = _vote_history_rows_from_raw(raw, "ts:X", self._now())
        assert len(rows) == 3
        types_years = {(r["election_type"], r["election_year"]) for r in rows}
        assert types_years == {("general", 2024), ("general", 2022), ("primary", 2024)}


# PySpark-gated end-to-end tests.
pyspark = pytest.importorskip("pyspark", reason="pyspark not installed; end-to-end tests skipped")


FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "ts_with_history.csv"


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    import os
    warehouse_root = tmp_path_factory.mktemp("warehouse-history")
    os.environ["SW_WAREHOUSE_ROOT"] = f"file://{warehouse_root}"

    from pyspark.sql import SparkSession
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("sw260-ts-vote-history-test")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


class TestExtractVoteHistory:
    def test_extracts_from_fixture(self, spark):
        from swh.voters.ts.bronze import ingest_bronze
        from swh.voters.ts.silver import build_silver_persons
        from swh.voters.ts.vote_history import extract_vote_history

        n_bronze = ingest_bronze(spark, csv_path=FIXTURE, state="TX")
        assert n_bronze == 4
        # Need persons rows to exist for compute_aggregates to merge against.
        build_silver_persons(spark)

        n_history = extract_vote_history(spark)
        # Expected event count from fixture:
        # SV001: g2024, g2022, g2020, g2018, p2024, p2022 = 6
        # RV001: g2024, g2022, p2024 = 3
        # OV001: g2024 = 1
        # NV001: (none) = 0
        # Total = 10
        assert n_history == 10

    def test_extract_idempotent(self, spark):
        from swh.voters.ts.vote_history import extract_vote_history
        n_again = extract_vote_history(spark)
        assert n_again == 10


class TestComputeAggregates:
    def test_aggregates_super_voter(self, spark):
        from socialwarehouse.delta.tables import TABLES
        from swh.voters.ts.vote_history import compute_aggregates

        n_updated = compute_aggregates(spark)
        assert n_updated == 3  # only the 3 voters with any history

        df = spark.read.format("delta").load(TABLES["silver.persons"]["path"])
        sv = df.filter(df.vendor_voter_id == "SV001").collect()[0]
        assert sv.general_election_count == 4
        assert sv.primary_election_count == 2
        assert sv.total_vote_count == 6
        assert sv.vote_frequency_category == "super_voter"
        assert sv.last_voted_at == date(2024, 11, 5)

    def test_aggregates_regular(self, spark):
        from socialwarehouse.delta.tables import TABLES
        df = spark.read.format("delta").load(TABLES["silver.persons"]["path"])
        rv = df.filter(df.vendor_voter_id == "RV001").collect()[0]
        assert rv.general_election_count == 2
        assert rv.vote_frequency_category == "regular"

    def test_aggregates_occasional(self, spark):
        from socialwarehouse.delta.tables import TABLES
        df = spark.read.format("delta").load(TABLES["silver.persons"]["path"])
        ov = df.filter(df.vendor_voter_id == "OV001").collect()[0]
        assert ov.general_election_count == 1
        assert ov.vote_frequency_category == "occasional"
