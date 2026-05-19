"""Regression test for S3 (SW#133): load_voter_file uses explicit
ACCESS EXCLUSIVE LOCK before DROP+RENAME during atomic table swap.

File-text source-grep (writing-tests:6 / claude-configs-public#123).
A live concurrency test against a real Postgres would need a fixture
that exercises a concurrent reader during the swap; out of session
scope. The source-grep regression goes red if anyone removes the LOCK
or moves it after the DROP.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

import swh.voters as _voters_mod

_SRC = Path(_voters_mod.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestLockBeforeDropRename(SimpleTestCase):

    def test_lock_table_in_code(self):
        assert "LOCK TABLE" in _CODE, (
            "Post-S3 fix expected `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE` "
            "before DROP+RENAME. (SW#133)"
        )

    def test_access_exclusive_mode(self):
        assert "ACCESS EXCLUSIVE MODE" in _CODE, (
            "Post-S3 fix expected explicit ACCESS EXCLUSIVE MODE lock "
            "qualifier. (SW#133)"
        )

    def test_lock_appears_before_drop_in_swap_block(self):
        # Find the LOCK occurrence and the swap-block's DROP TABLE IF EXISTS.
        lock_idx = _CODE.find("LOCK TABLE")
        drop_idx = _CODE.find("DROP TABLE IF EXISTS")
        rename_idx = _CODE.find("ALTER TABLE")
        assert -1 < lock_idx < drop_idx < rename_idx, (
            f"Order must be LOCK -> DROP -> RENAME within the swap block. "
            f"Got LOCK@{lock_idx} DROP@{drop_idx} RENAME@{rename_idx}."
        )

    def test_has_table_check_before_lock(self):
        # has_table check guards first-ever loads where target does not exist.
        # Without this, LOCK would error.
        assert "has_table(" in _CODE, (
            "Post-S3 fix expected inspect(engine).has_table(...) pre-check "
            "to guard first-ever-load case where target doesn't exist yet. "
            "(SW#133)"
        )
        has_table_idx = _CODE.find("has_table(")
        lock_idx = _CODE.find("LOCK TABLE")
        assert -1 < has_table_idx < lock_idx, (
            "has_table check must precede the LOCK TABLE statement."
        )

    def test_lock_is_conditional_on_target_exists(self):
        # The LOCK must be guarded by a conditional referencing the
        # target-existence check; otherwise first-ever loads fail.
        # Heuristic: the line preceding LOCK TABLE should contain "if " and
        # a variable referencing the existence check.
        lines = _CODE.splitlines()
        for i, line in enumerate(lines):
            if "LOCK TABLE" in line:
                # Look at the preceding non-blank line for an `if` guard.
                for j in range(i - 1, max(-1, i - 5), -1):
                    if lines[j].strip():
                        assert "if " in lines[j], (
                            f"LOCK TABLE on line {i} must be guarded by an "
                            f"`if target_exists`-style conditional; "
                            f"preceding line was: {lines[j]!r}"
                        )
                        return
        # If we got here, no LOCK TABLE was found -- already covered by
        # test_lock_table_in_code.
