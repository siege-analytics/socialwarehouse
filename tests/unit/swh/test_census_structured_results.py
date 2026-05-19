"""Regression test for S1 (SW#131): download_census_boundaries and
load_census_to_postgis return structured DownloadResult / LoadResult
NamedTuples with explicit successes + failures dicts.

Pre-fix the functions returned bare `dict[str, ...]`; per-boundary-type
failures were silent (the result dict simply lacked the failed key).
"""

import re
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

import swh.census as census_mod

_SRC = Path(census_mod.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestResultTypesExist(SimpleTestCase):

    def test_download_result_namedtuple(self):
        from swh.census import DownloadResult

        result = DownloadResult(successes={}, failures={})
        assert hasattr(result, "successes")
        assert hasattr(result, "failures")
        assert hasattr(result, "any_failed")
        assert hasattr(result, "all_failed")
        assert result.any_failed is False
        assert result.all_failed is False

    def test_load_result_namedtuple(self):
        from swh.census import LoadResult

        result = LoadResult(successes={}, failures={})
        assert hasattr(result, "successes")
        assert hasattr(result, "failures")
        assert hasattr(result, "any_failed")

    def test_any_failed_property(self):
        from swh.census import DownloadResult, LoadResult

        d = DownloadResult(successes={"county": mock.MagicMock()}, failures={})
        assert d.any_failed is False

        d = DownloadResult(successes={}, failures={"county": RuntimeError("x")})
        assert d.any_failed is True
        assert d.all_failed is True

        d = DownloadResult(
            successes={"county": mock.MagicMock()},
            failures={"cd": RuntimeError("x")},
        )
        assert d.any_failed is True
        assert d.all_failed is False

        l = LoadResult(successes={"county": "county_48"}, failures={})
        assert l.any_failed is False
        l = LoadResult(successes={}, failures={"county": RuntimeError("x")})
        assert l.any_failed is True


class TestSourceShape(SimpleTestCase):

    def test_no_bare_dict_return_on_download(self):
        # Pre-fix: returned `dict[str, gpd.GeoDataFrame]`. Post-fix returns
        # DownloadResult. The function signature must reflect that.
        assert "-> DownloadResult" in _CODE, (
            "download_census_boundaries must return DownloadResult, not "
            "a bare dict (S1 / SW#131)."
        )
        assert "-> LoadResult" in _CODE, (
            "load_census_to_postgis must return LoadResult, not a bare "
            "dict (S1 / SW#131)."
        )

    def test_failures_dict_is_populated(self):
        # In the except block, failures dict must get the exception added.
        # Pre-fix only logged via logger.exception; post-fix must also
        # populate the failures dict.
        assert "failures[boundary_type] = e" in _CODE, (
            "except block must record the exception in failures dict "
            "(S1 / SW#131); merely logging is the pre-fix anti-pattern."
        )

    def test_load_handles_upload_false_return(self):
        # upload_spatial_data returns False on failure without raising.
        # The post-fix load must convert False -> failures entry.
        assert "returned False" in _CODE or "upload_spatial_data returned" in _CODE, (
            "post-fix must handle upload_spatial_data's False return as "
            "a failure (S1 / SW#131)."
        )