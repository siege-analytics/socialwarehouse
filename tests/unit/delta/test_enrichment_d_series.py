"""Regression tests for D1+D2+D3 fixes in delta/enrichment.py.

D1 (SW#123): SQL string interpolation of `year` parameter removed.
D2 (SW#124): county + cd joins now contribute to returned DataFrame.
D3 (SW#125): `.count()` no longer inside log messages.

Tests are source-grep based (file-text read, not inspect.getsource per
claude-configs-public#123 inspection-vs-behavior rule-gap). Live Spark
behavior tests are not in this PR -- Sedona/Spark is not in the unit-test
matrix, and adding it is a separate scope. The source-grep regressions
go red on revert of any of the three findings.
"""

from pathlib import Path

from django.test import SimpleTestCase

from socialwarehouse.delta import enrichment

_SRC = Path(enrichment.__file__).read_text(encoding="utf-8")


def _function_block(name):
    """Return decorator stack + def + body for a top-level function."""
    lines = _SRC.splitlines()
    def_idx = next((i for i, line in enumerate(lines) if line.startswith(f"def {name}(")), None)
    if def_idx is None:
        return ""
    start = def_idx
    while start > 0 and lines[start - 1].startswith("@"):
        start -= 1
    end = def_idx + 1
    while end < len(lines) and not (
        lines[end].startswith("def ") or lines[end].startswith("class ")
    ):
        end += 1
    return "\n".join(lines[start:end])


class TestD1NoSqlYearInterpolation(SimpleTestCase):
    """D1: `year` must not be interpolated into Spark SQL strings."""

    def test_no_format_year_in_enrichment_block(self):
        block = _function_block("enrich_addresses_with_boundaries")
        assert block, "enrich_addresses_with_boundaries not found in source"
        # The pre-fix shape: .format(year=year) on a triple-quoted SQL string.
        assert ".format(year=year)" not in block, (
            "year must not be interpolated into Spark SQL via .format() "
            "(D1/SW#123). Pre-filter boundaries via DataFrame API instead."
        )

    def test_no_fstring_year_in_filter(self):
        block = _function_block("enrich_addresses_with_boundaries")
        # The pre-fix shape: f"vintage_year = {year}" inside .filter()
        assert 'f"vintage_year = {year}"' not in block, (
            "Pre-filter boundaries by year via F.col equality, not f-string "
            "filter expression (D1/SW#123)."
        )

    def test_uses_dataframe_api_for_year_filter(self):
        block = _function_block("enrich_addresses_with_boundaries")
        # Post-fix uses F.col("vintage_year") == year
        assert 'F.col("vintage_year") == year' in block, (
            "Expected DataFrame-API filter F.col(\"vintage_year\") == year "
            "after D1/SW#123 fix"
        )


class TestD2EnrichmentReturnsAllJoins(SimpleTestCase):
    """D2: county and cd joins must contribute to the returned DataFrame."""

    def test_returns_chained_enrichment(self):
        block = _function_block("enrich_addresses_with_boundaries")
        # Post-fix returns `enriched` (the chain output), not `state_join`.
        assert "return enriched" in block, (
            "Expected `return enriched` (chained state/county/cd DataFrame) "
            "after D2/SW#124 fix"
        )
        assert "return state_join" not in block, (
            "`return state_join` discards county and cd joins (D2/SW#124)"
        )

    def test_county_columns_in_select(self):
        block = _function_block("enrich_addresses_with_boundaries")
        assert "county_geoid" in block and "county_name" in block, (
            "Post-D2 enriched DataFrame must surface county_geoid and "
            "county_name columns"
        )

    def test_cd_columns_in_select(self):
        block = _function_block("enrich_addresses_with_boundaries")
        assert "cd_geoid" in block and "cd_name" in block, (
            "Post-D2 enriched DataFrame must surface cd_geoid and cd_name"
        )

    def test_uses_left_join_consistently(self):
        block = _function_block("enrich_addresses_with_boundaries")
        # Post-fix: LEFT JOIN for all three. Pre-fix: state was LEFT, county
        # and cd were INNER. Going red if anyone re-introduces INNER.
        # Heuristic: counted LEFT JOIN occurrences in the function body
        # should be at least 3 (state, county, cd). Plain `JOIN` (without LEFT)
        # against boundaries should not appear.
        assert block.count("LEFT JOIN boundaries") == 3, (
            f"Expected 3 LEFT JOIN boundaries in enrichment chain, "
            f"got {block.count('LEFT JOIN boundaries')} (D2/D6 fix)"
        )


class TestD3NoCountInLog(SimpleTestCase):
    """D3: `.count()` must not appear inside logger calls.

    Comments mentioning `.count()` (e.g. the post-fix explanatory comment)
    are allowed; only code-side `.count()` inside a `logger.<level>(...)`
    argument list is the regression target.
    """

    def test_no_count_in_logger_args(self):
        import re

        block = _function_block("enrich_addresses_with_boundaries")
        # Strip comment-only lines and inline-trailing comments before grep.
        code_lines = []
        for line in block.splitlines():
            stripped = line.split("#", 1)[0]
            if stripped.strip():
                code_lines.append(stripped)
        code = "\n".join(code_lines)
        # Look for logger.<anything>(...) calls and check their argument
        # span for `.count(`. Spark `.count()` is the regression target.
        pattern = re.compile(r"logger\.\w+\s*\((.*?)\)", re.DOTALL)
        for match in pattern.finditer(code):
            args = match.group(1)
            assert ".count(" not in args, (
                f".count() is a Spark action; do not invoke inside a logger "
                f"call (D3/SW#125). Offending call args:\n{args!r}"
            )
