"""Regression test for M6 (SW#150): geocode_addresses Phase-1 enforces
the invariant `geocoded=True implies geom IS NOT NULL`.

Pre-fix: Census `matched=True` flipped `geocoded=True` regardless of
whether lat/lon were populated. Post-fix: matched-without-coords is
demoted to the unmatched bucket.

Source-grep regression (writing-tests:6 carve-out): the actual control
flow lives inside a management-command handle() with heavy DB/HTTP
fixtures; we assert the structural property that the matched branch
requires lat AND lon at the condition.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from socialwarehouse.geo.management.commands import geocode_addresses as _mod


_SRC = Path(_mod.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestM6CoordsRequiredForGeocoded(SimpleTestCase):

    def test_matched_branch_requires_lat_and_lon(self):
        # Post-M6: the condition for entering the "mark geocoded=True"
        # branch must include result.lat AND result.lon, not just
        # result.matched.
        assert re.search(
            r"if\s+result\.matched\s+and\s+result\.lat\s+and\s+result\.lon\s*:",
            _CODE,
        ), (
            "Post-M6/SW#150 condition not found: expected "
            "'if result.matched and result.lat and result.lon:' guard"
        )

    def test_no_bare_matched_only_branch(self):
        # The pre-fix shape was `if result.matched:` followed by a
        # nested `if result.lat and result.lon:` only on the geom
        # assignment. The post-fix removes that pattern by moving the
        # coord check up to the outer condition.
        # Match: any line that is exactly `if result.matched:` (no AND).
        assert not re.search(
            r"^\s*if\s+result\.matched\s*:\s*$",
            _CODE,
            flags=re.MULTILINE,
        ), (
            "Pre-M6 bare `if result.matched:` branch is back. "
            "matched=True without coords must be demoted to unmatched."
        )
