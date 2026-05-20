"""Regression test for D5 (SW#127): delta/config.py validates S3
credentials at module-load time when WAREHOUSE_ROOT requires S3.

Behavior tests: re-import the module under different env var
combinations and assert it raises (or doesn't) as designed.
"""

import importlib
import os
import sys

from django.test import SimpleTestCase


def _reimport_config(env):
    """Reload socialwarehouse.delta.config under the given env dict."""
    saved = {k: os.environ.get(k) for k in
             ("SW_WAREHOUSE_ROOT", "S3_ACCESS_KEY", "S3_SECRET_KEY")}
    try:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("socialwarehouse.delta.config", None)
        return importlib.import_module("socialwarehouse.delta.config")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("socialwarehouse.delta.config", None)


class TestD5CredentialValidation(SimpleTestCase):

    def test_s3a_root_missing_both_creds_raises(self):
        with self.assertRaises(RuntimeError) as cm:
            _reimport_config({
                "SW_WAREHOUSE_ROOT": "s3a://bucket",
                "S3_ACCESS_KEY": "",
                "S3_SECRET_KEY": "",
            })
        msg = str(cm.exception)
        assert "S3_ACCESS_KEY" in msg
        assert "S3_SECRET_KEY" in msg
        assert "D5" in msg or "SW#127" in msg

    def test_s3a_root_missing_only_secret_raises(self):
        with self.assertRaises(RuntimeError) as cm:
            _reimport_config({
                "SW_WAREHOUSE_ROOT": "s3a://bucket",
                "S3_ACCESS_KEY": "key",
                "S3_SECRET_KEY": "",
            })
        assert "S3_SECRET_KEY" in str(cm.exception)
        assert "S3_ACCESS_KEY" not in str(cm.exception)

    def test_s3_scheme_also_validated(self):
        with self.assertRaises(RuntimeError):
            _reimport_config({
                "SW_WAREHOUSE_ROOT": "s3://bucket",
                "S3_ACCESS_KEY": "",
                "S3_SECRET_KEY": "",
            })

    def test_s3n_scheme_also_validated(self):
        with self.assertRaises(RuntimeError):
            _reimport_config({
                "SW_WAREHOUSE_ROOT": "s3n://bucket",
                "S3_ACCESS_KEY": "",
                "S3_SECRET_KEY": "",
            })

    def test_file_root_skips_validation(self):
        mod = _reimport_config({
            "SW_WAREHOUSE_ROOT": "file:///tmp/sw-warehouse",
            "S3_ACCESS_KEY": "",
            "S3_SECRET_KEY": "",
        })
        assert mod.WAREHOUSE_ROOT == "file:///tmp/sw-warehouse"

    def test_s3a_root_with_both_creds_succeeds(self):
        mod = _reimport_config({
            "SW_WAREHOUSE_ROOT": "s3a://bucket",
            "S3_ACCESS_KEY": "k",
            "S3_SECRET_KEY": "s",
        })
        assert mod.S3_ACCESS_KEY == "k"
        assert mod.S3_SECRET_KEY == "s"
