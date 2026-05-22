"""
Tests for SW#265 (B.5 of #250): address backfill.

Django-DB tests cover the per-row Address lookup helper. PySpark +
django-db tests cover the end-to-end `backfill_addresses` against a
fixture where lat/lon match a known Address row.
"""

from decimal import Decimal
from pathlib import Path

import pytest


class TestChunkHelper:
    def test_yields_chunks(self):
        from swh.voters.address_backfill import _chunk
        assert list(_chunk([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_empty_input(self):
        from swh.voters.address_backfill import _chunk
        assert list(_chunk([], 5)) == []


@pytest.mark.django_db
class TestFindAddressId:
    def _make_address(self, lat, lon, state="TX"):
        from socialwarehouse.geo.models import Address
        return Address.objects.create(
            state_abbreviation=state,
            latitude=Decimal(str(lat)),
            longitude=Decimal(str(lon)),
        )

    def test_exact_match(self):
        from swh.voters.address_backfill import _find_address_id
        a = self._make_address(30.2672, -97.7431)
        assert _find_address_id(30.2672, -97.7431) == a.id

    def test_within_tolerance(self):
        from swh.voters.address_backfill import _find_address_id
        # Address at known lat/lon
        a = self._make_address(30.2672, -97.7431)
        # Query at a slightly different position within default tolerance (0.00001)
        match = _find_address_id(30.26720001, -97.74310001)
        assert match == a.id

    def test_outside_tolerance(self):
        from swh.voters.address_backfill import _find_address_id
        self._make_address(30.2672, -97.7431)
        # Far enough away that default tolerance won't catch it
        assert _find_address_id(30.30, -97.80) is None

    def test_no_addresses_returns_none(self):
        from swh.voters.address_backfill import _find_address_id
        assert _find_address_id(30.0, -97.0) is None

    def test_multiple_matches_picks_lowest_id(self):
        from swh.voters.address_backfill import _find_address_id
        a1 = self._make_address(30.2672, -97.7431)
        a2 = self._make_address(30.2672, -97.7431)
        match = _find_address_id(30.2672, -97.7431)
        assert match == a1.id
        assert match < a2.id


@pytest.mark.django_db
class TestResolveAddresses:
    def test_resolves_only_rows_with_lat_lon(self):
        from socialwarehouse.geo.models import Address
        from swh.voters.address_backfill import _resolve_addresses

        a = Address.objects.create(
            state_abbreviation="TX",
            latitude=Decimal("30.2672"),
            longitude=Decimal("-97.7431"),
        )
        rows = [
            {"person_key": "ts:HAS-COORDS", "latitude": 30.2672, "longitude": -97.7431},
            {"person_key": "ts:NO-COORDS", "latitude": None, "longitude": None},
            {"person_key": "ts:NO-MATCH", "latitude": 50.0, "longitude": 10.0},
        ]
        resolved = _resolve_addresses(rows, tolerance=0.00001)
        assert resolved == {"ts:HAS-COORDS": a.id}


# PySpark + Django-DB end-to-end
pyspark = pytest.importorskip("pyspark", reason="pyspark not installed; backfill end-to-end test skipped")


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    import os
    warehouse_root = tmp_path_factory.mktemp("warehouse-backfill")
    os.environ["SW_WAREHOUSE_ROOT"] = f"file://{warehouse_root}"

    from pyspark.sql import SparkSession
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("sw265-address-backfill-test")
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
class TestBackfillEndToEnd:
    def test_backfill_links_dimperson_to_address(self, spark):
        from decimal import Decimal

        from socialwarehouse.geo.models import Address
        from socialwarehouse.warehouse.models import DimPerson
        from swh.voters.address_backfill import backfill_addresses
        from swh.voters.materialize import materialize_persons
        from swh.voters.ts.bronze import ingest_bronze
        from swh.voters.ts.silver import build_silver_persons

        fixtures = Path(__file__).resolve().parents[3] / "fixtures"

        # Create a canonical Address at Ada's known TS lat/lon (TS001
        # row in ts_sample.csv: 30.2672, -97.7431).
        addr = Address.objects.create(
            state_abbreviation="TX",
            latitude=Decimal("30.2672"),
            longitude=Decimal("-97.7431"),
        )

        # Ingest the spine + materialize DimPerson with address=null
        ingest_bronze(spark, csv_path=fixtures / "ts_sample.csv", state="TX")
        build_silver_persons(spark)
        materialize_persons(spark)

        ada = DimPerson.objects.get(vendor="ts", vendor_voter_id="TS001")
        assert ada.address_id is None  # not yet backfilled

        counts = backfill_addresses(spark)
        assert counts["postgis_updated"] >= 1
        assert counts["silver_updated"] >= 1

        ada.refresh_from_db()
        assert ada.address_id == addr.id

    def test_backfill_idempotent_already_linked(self, spark):
        from socialwarehouse.warehouse.models import DimPerson
        from swh.voters.address_backfill import backfill_addresses

        # Ada is already linked. Re-running silver-WHERE-address_id-NULL
        # filter excludes her row, so the second pass is a no-op for her.
        counts = backfill_addresses(spark)
        ada = DimPerson.objects.get(vendor="ts", vendor_voter_id="TS001")
        assert ada.address_id is not None  # still linked
        # counts reflects only the persons still null after first pass —
        # the 9 fixture rows without a matching Address row stay null.
        assert counts["postgis_updated"] == 0
