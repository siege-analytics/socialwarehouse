"""Regression test for D4 (SW#126): get_spark_session is no longer
decorated with @lru_cache. The Spark singleton mechanism is
SparkSession.builder.getOrCreate(), not Python-side memoization.

Source-grep + signature inspection. Comment + docstring stripping per
writing-tests:6 / claude-configs-public#123.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from socialwarehouse.delta import config as _cfg

_SRC = Path(_cfg.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestNoLruCacheDecorator(SimpleTestCase):

    def test_lru_cache_not_imported(self):
        assert "from functools import lru_cache" not in _CODE, (
            "lru_cache import was removed in D4/SW#126 fix; re-adding "
            "implies someone re-decorated get_spark_session, which "
            "reintroduces the eviction-without-stop leak."
        )

    def test_lru_cache_not_applied_to_get_spark_session(self):
        # Find the def-line and walk backwards through decorators; none
        # should be @lru_cache.
        lines = _CODE.splitlines()
        def_idx = next(
            (i for i, l in enumerate(lines) if l.startswith("def get_spark_session(")),
            None,
        )
        assert def_idx is not None, "could not find def get_spark_session"
        decorators = []
        for i in range(def_idx - 1, -1, -1):
            stripped = lines[i].strip()
            if not stripped:
                break
            if stripped.startswith("@"):
                decorators.append(stripped)
            else:
                break
        for dec in decorators:
            assert "lru_cache" not in dec, (
                f"get_spark_session must not be @lru_cache decorated "
                f"(D4/SW#126). Found: {dec}"
            )

    def test_get_spark_session_function_object_has_no_cache(self):
        # functools.lru_cache attaches .cache_info() and .cache_clear() to
        # the wrapped function. If those exist, lru_cache is still applied.
        fn = _cfg.get_spark_session
        assert not hasattr(fn, "cache_info"), (
            "get_spark_session has .cache_info() — implies @lru_cache is "
            "still applied. Should be a plain function (D4/SW#126)."
        )
        assert not hasattr(fn, "cache_clear"), (
            "get_spark_session has .cache_clear() — implies @lru_cache is "
            "still applied. Should be a plain function (D4/SW#126)."
        )
