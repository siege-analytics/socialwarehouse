"""Regression test for S2 (SW#132): load_voter_file and
voter_file_to_geodataframe pass explicit encoding / dtype / quoting kwargs
to pandas.read_csv.

Source-grep + a unit test that calls the functions with a mocked
pd.read_csv to verify kwargs flow through. Comment + docstring stripping
per writing-tests:6 / claude-configs-public#123.
"""

import csv
import inspect as py_inspect
import re
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

import swh.voters._legacy_raw as voters_mod

_SRC = Path(voters_mod.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestModuleConstantsExist(SimpleTestCase):

    def test_targetsmart_default_dtypes_constant(self):
        assert hasattr(voters_mod, "TARGETSMART_DEFAULT_DTYPES")
        d = voters_mod.TARGETSMART_DEFAULT_DTYPES
        assert isinstance(d, dict)
        # Spot-check the ID columns that pandas would silently auto-type
        # as float64 without an explicit dtype.
        for key in (
            "vb_vf_national_precinct_code",
            "vb_vf_cd",
            "vb_vf_sd",
            "vb_vf_hd",
            "zip5",
            "county_fips",
        ):
            assert key in d, f"Expected {key} in TARGETSMART_DEFAULT_DTYPES"
            assert d[key] is str, f"Expected str dtype for {key}, got {d[key]!r}"

    def test_default_csv_encoding_constant(self):
        assert hasattr(voters_mod, "DEFAULT_CSV_ENCODING")
        assert voters_mod.DEFAULT_CSV_ENCODING == "utf-8-sig", (
            "BOM-tolerant default expected; TargetSmart exports include BOM."
        )


class TestPublicReadPathsAcceptCsvKwargs(SimpleTestCase):
    """Both public functions must accept encoding / dtype / quoting /
    quotechar kwargs with sensible defaults."""

    def _assert_kwarg_with_default(self, fn, kwarg, expected_default):
        sig = py_inspect.signature(fn)
        assert kwarg in sig.parameters, f"{fn.__name__} missing kwarg {kwarg}"
        actual_default = sig.parameters[kwarg].default
        assert actual_default == expected_default, (
            f"{fn.__name__}.{kwarg} default: expected {expected_default!r}, "
            f"got {actual_default!r}"
        )

    def test_load_voter_file_signature(self):
        fn = voters_mod.load_voter_file
        self._assert_kwarg_with_default(fn, "encoding", "utf-8-sig")
        self._assert_kwarg_with_default(fn, "dtype", None)
        self._assert_kwarg_with_default(fn, "quoting", csv.QUOTE_MINIMAL)
        self._assert_kwarg_with_default(fn, "quotechar", '"')

    def test_voter_file_to_geodataframe_signature(self):
        fn = voters_mod.voter_file_to_geodataframe
        self._assert_kwarg_with_default(fn, "encoding", "utf-8-sig")
        self._assert_kwarg_with_default(fn, "dtype", None)
        self._assert_kwarg_with_default(fn, "quoting", csv.QUOTE_MINIMAL)
        self._assert_kwarg_with_default(fn, "quotechar", '"')


class TestSourceShape(SimpleTestCase):

    def test_csv_module_imported(self):
        assert "import csv" in _CODE, "csv stdlib import expected (QUOTE_MINIMAL)"

    def test_pd_read_csv_passes_kwargs(self):
        # Two pd.read_csv call sites in module; both must pass the kwargs.
        # Look for `encoding=encoding` (literal kwarg-pass-through) inside
        # at least 2 pd.read_csv blocks.
        # Heuristic: count `encoding=encoding` occurrences.
        assert _CODE.count("encoding=encoding") >= 2, (
            "Both load_voter_file and voter_file_to_geodataframe must pass "
            "encoding through to pd.read_csv (S2 / SW#132)."
        )
        assert _CODE.count("dtype=dtype") >= 2, (
            "Both functions must pass dtype through to pd.read_csv "
            "(S2 / SW#132)."
        )

    def test_no_bare_read_csv_anymore(self):
        # The pre-fix shape was `pd.read_csv(filepath)` and
        # `pd.read_csv(filepath, chunksize=chunk_size)`. Post-fix, every
        # pd.read_csv call site should also pass encoding/dtype.
        # Approximation: find every pd.read_csv( and verify the call's
        # argument span includes "encoding=".
        for m in re.finditer(r"pd\.read_csv\(([^)]*)\)", _CODE, re.DOTALL):
            args = m.group(1)
            assert "encoding=" in args, (
                f"pd.read_csv call missing encoding kwarg: {args!r}"
            )