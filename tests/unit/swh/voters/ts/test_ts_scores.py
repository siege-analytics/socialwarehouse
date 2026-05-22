"""
Tests for SW#259: TargetSmart score extraction.

Pure-Python tests cover the score-mapping table + the per-row score
extraction helper. Spark-gated tests cover the end-to-end extract_scores
against the existing fixture (which includes vb.tsmart_partisan_score
and vb.tsmart_climate_score).
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest


class TestScoreMappings:
    """Mapping resolution — no Spark required."""

    def test_static_partisan(self):
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_partisan_score", "ts-2024") == ("partisan_score", "ts-2024")

    def test_static_climate_becomes_issue_climate(self):
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_climate_score", "ts-2024") == ("issue_climate", "ts-2024")

    def test_static_methodology_respects_default(self):
        from swh.voters.ts.score_mappings import lookup
        out = lookup("vb.tsmart_partisan_score", "ts-2026")
        assert out == ("partisan_score", "ts-2026")

    def test_cycle_aligned_turnout_general(self):
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_turnout_score_general_2024", "ts-2024") == (
            "turnout_propensity_general", "ts-2024"
        )

    def test_cycle_aligned_turnout_primary_different_cycle(self):
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_turnout_score_primary_2022", "ts-2024") == (
            "turnout_propensity_primary", "ts-2022"
        )

    def test_unknown_returns_none(self):
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_made_up_score", "ts-2024") is None

    def test_non_score_column_returns_none(self):
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_first_name", "ts-2024") is None

    def test_cycle_with_non_year_suffix_returns_none(self):
        # `vb.tsmart_turnout_score_general_foo` — not a 4-digit year.
        from swh.voters.ts.score_mappings import lookup
        assert lookup("vb.tsmart_turnout_score_general_foo", "ts-2024") is None


class TestScoreRowEmission:
    """_score_rows_from_raw extracts rows from a parsed TS payload."""

    def _now(self):
        return datetime(2026, 5, 22, tzinfo=timezone.utc)

    def test_emits_static_score(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {"vb.tsmart_partisan_score": "72"}
        rows = _score_rows_from_raw(raw, "ts:TS001", self._now(), self._now(), "ts-2024")
        assert len(rows) == 1
        r = rows[0]
        assert r["person_key"] == "ts:TS001"
        assert r["score_type"] == "partisan_score"
        assert r["value"] == 72.0
        assert r["source_vendor"] == "ts"
        assert r["methodology_version"] == "ts-2024"

    def test_skips_unmapped(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {"vb.tsmart_made_up_score": "5"}
        rows = _score_rows_from_raw(raw, "ts:X", self._now(), self._now(), "ts-2024")
        assert rows == []

    def test_skips_non_score_fields(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {"vb.tsmart_first_name": "Ada"}
        rows = _score_rows_from_raw(raw, "ts:X", self._now(), self._now(), "ts-2024")
        assert rows == []

    def test_skips_unparseable_value(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {"vb.tsmart_partisan_score": "not-a-number"}
        rows = _score_rows_from_raw(raw, "ts:X", self._now(), self._now(), "ts-2024")
        assert rows == []

    def test_skips_empty_value(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {"vb.tsmart_partisan_score": ""}
        rows = _score_rows_from_raw(raw, "ts:X", self._now(), self._now(), "ts-2024")
        assert rows == []

    def test_emits_multiple_scores_per_row(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {
            "vb.tsmart_partisan_score": "72",
            "vb.tsmart_climate_score": "55",
            "vb.tsmart_turnout_score_general_2024": "0.85",
            "vb.tsmart_first_name": "Ada",  # ignored
        }
        rows = _score_rows_from_raw(raw, "ts:TS001", self._now(), self._now(), "ts-2024")
        types = {r["score_type"] for r in rows}
        assert types == {"partisan_score", "issue_climate", "turnout_propensity_general"}

    def test_emits_cycle_methodology_per_cycle(self):
        from swh.voters.ts.scores import _score_rows_from_raw
        raw = {
            "vb.tsmart_turnout_score_general_2020": "0.5",
            "vb.tsmart_turnout_score_general_2024": "0.8",
        }
        rows = _score_rows_from_raw(raw, "ts:X", self._now(), self._now(), "ts-2024")
        # Same score_type, different methodology_version per cycle.
        methodologies = {r["methodology_version"] for r in rows}
        assert methodologies == {"ts-2020", "ts-2024"}


# PySpark-gated end-to-end tests.
pyspark = pytest.importorskip("pyspark", reason="pyspark not installed; end-to-end tests skipped")


FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "ts_sample.csv"


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    import os
    warehouse_root = tmp_path_factory.mktemp("warehouse-scores")
    os.environ["SW_WAREHOUSE_ROOT"] = f"file://{warehouse_root}"

    from pyspark.sql import SparkSession
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("sw259-ts-scores-test")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


class TestExtractScoresEndToEnd:
    def test_extract_scores_from_fixture(self, spark):
        from swh.voters.ts.bronze import ingest_bronze
        from swh.voters.ts.scores import extract_scores

        n_bronze = ingest_bronze(spark, csv_path=FIXTURE, state="TX")
        assert n_bronze == 10

        n_scores = extract_scores(spark, default_methodology="ts-2024")
        # Fixture has vb.tsmart_partisan_score + vb.tsmart_climate_score
        # populated for all 10 rows. Each row yields 2 score rows.
        assert n_scores == 20

    def test_extract_is_idempotent(self, spark):
        from swh.voters.ts.scores import extract_scores
        n_again = extract_scores(spark, default_methodology="ts-2024")
        # Still 20 rows; upsert leaves the table at the same row-count
        assert n_again == 20

    def test_scores_table_has_expected_rows(self, spark):
        from socialwarehouse.delta.tables import TABLES
        df = spark.read.format("delta").load(TABLES["silver.person_scores"]["path"])
        n_total = df.count()
        assert n_total == 20
        # Ada is fixture TS001 with partisan_score=72
        ada_partisan = df.filter(
            (df.person_key == "ts:TS001") & (df.score_type == "partisan_score")
        ).collect()
        assert len(ada_partisan) == 1
        assert ada_partisan[0].value == 72.0
        assert ada_partisan[0].source_vendor == "ts"
        assert ada_partisan[0].methodology_version == "ts-2024"
