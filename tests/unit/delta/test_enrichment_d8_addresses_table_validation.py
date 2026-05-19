"""Regression test for D8 (SW#130): enrich_addresses_with_boundaries
validates addresses_table against the TABLES registry, and only accepts
unknown values that look like raw paths (contain '/' or a scheme).

Behavior test — call the function with a bad addresses_table; assert
ValueError. We don't need a real SparkSession because the validation
runs before any Spark API is touched.
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from socialwarehouse.delta import enrichment as _enr
from socialwarehouse.delta.tables import TABLES


class TestD8AddressesTableValidation(SimpleTestCase):

    def test_typo_registry_key_raises_valueerror(self):
        # "silver.address" is a one-char typo of "silver.addresses".
        # Pre-fix this fell through to spark.read.load("silver.address").
        # Post-fix it raises ValueError naming the known keys.
        spark = MagicMock()
        with self.assertRaises(ValueError) as cm:
            _enr.enrich_addresses_with_boundaries(spark, "silver.address")
        msg = str(cm.exception)
        assert "silver.address" in msg
        assert "D8" in msg or "SW#130" in msg
        # Should mention at least one known key in the error.
        assert "silver.addresses" in msg or any(k in msg for k in TABLES.keys())

    def test_path_with_slash_passes_validation(self):
        # Raw filesystem-style path — should not raise from the
        # validator. (It will fail later in Spark — that's fine; we
        # only assert the validator doesn't reject the raw path.)
        spark = MagicMock()
        spark.read.format.return_value.load.return_value.filter.return_value = MagicMock()
        try:
            _enr.enrich_addresses_with_boundaries(spark, "/tmp/some/raw/path")
        except ValueError as e:
            if "D8" in str(e) or "SW#130" in str(e):
                self.fail(f"raw filesystem path incorrectly rejected by D8 validator: {e}")

    def test_path_with_scheme_passes_validation(self):
        spark = MagicMock()
        spark.read.format.return_value.load.return_value.filter.return_value = MagicMock()
        try:
            _enr.enrich_addresses_with_boundaries(spark, "s3a://bucket/path")
        except ValueError as e:
            if "D8" in str(e) or "SW#130" in str(e):
                self.fail(f"s3a:// path incorrectly rejected by D8 validator: {e}")

    def test_known_registry_key_passes_validation(self):
        spark = MagicMock()
        spark.read.format.return_value.load.return_value.filter.return_value = MagicMock()
        # Use whatever key is in TABLES.
        known_key = next(iter(TABLES.keys()))
        try:
            _enr.enrich_addresses_with_boundaries(spark, known_key)
        except ValueError as e:
            if "D8" in str(e) or "SW#130" in str(e):
                self.fail(f"known registry key incorrectly rejected by D8 validator: {e}")
