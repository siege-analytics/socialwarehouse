"""Regression tests for M1+M2+M3 fixes in geocode_addresses.py.

M1 (SW#145): no qs.count() before iterator() (re-execution antipattern).
M2 (SW#146): no per-row addr.save() inside the loop; uses bulk_update.
M3 (SW#147): no full materialization before chunked-API call; streams chunks.

Source-grep tests strip comments before matching (per
claude-configs-public#123 inspection-vs-behavior rule + writing-tests:6).
A live Django test that actually runs the command is out of scope for
this PR; the source-grep regressions catch the antipatterns going red on
revert.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from socialwarehouse.geo.management.commands import geocode_addresses as _cmd

_SRC = Path(_cmd.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    """Best-effort strip of Python comments and triple-quoted docstrings.

    Not a full AST pass; sufficient to prevent post-fix explanatory
    comments / docstrings from matching the pre-fix-shape source-greps.
    """
    # Strip triple-quoted docstrings (greedy across newlines).
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    # Strip line comments.
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestM1NoCountBeforeIterator(SimpleTestCase):
    """M1: qs.count() must not be followed by iterator() in the same flow.

    Pre-fix: `total = qs.count()` then later `for addr in addr_qs.iterator()`
    re-executed the SELECT. The fix removes the pre-loop count entirely
    (dry-run path may still call count() since it doesn't iterate).
    """

    def test_handle_does_not_call_qs_count_in_main_path(self):
        # The handle() body should not contain "= qs.count()" or similar
        # before the iteration begins. The dry-run path is allowed to call
        # count() because it does not iterate.
        # Heuristic: count occurrences of `.count()` in code; should be at
        # most 1 (the dry-run path). Pre-fix had 2.
        count_occurrences = _CODE.count(".count()")
        assert count_occurrences <= 1, (
            f"Expected at most 1 .count() call (dry-run only), got "
            f"{count_occurrences}. M1/SW#145 fix removed the pre-iterator "
            f"count which caused query re-execution."
        )

    def test_no_total_variable_assigned_from_qs_count(self):
        # Word-boundary-anchored regex so this doesn't match "dry_total =
        # qs.count()" (the dry-run path's local variable, allowed because
        # dry-run does not iterate).
        offending = re.search(r"(?<![_A-Za-z])total\s*=\s*qs\.count\(\)", _CODE)
        assert offending is None, (
            "Pre-fix pattern: total = qs.count() then iterator() re-executes. "
            "M1/SW#145 fix removed it. (dry_total in the dry-run path is "
            "allowed by the boundary regex.)"
        )


class TestM2NoPerRowSave(SimpleTestCase):
    """M2: addr.save() inside the per-result loop is the antipattern.

    Post-fix uses Address.objects.bulk_update on accumulated chunks.
    """

    def test_no_addr_save_in_code(self):
        assert "addr.save()" not in _CODE, (
            "M2/SW#146 fix: per-row addr.save() in a batch loop is wrong. "
            "Use Address.objects.bulk_update on accumulated chunks."
        )

    def test_uses_bulk_update(self):
        assert "Address.objects.bulk_update(" in _CODE, (
            "M2/SW#146 fix expected Address.objects.bulk_update for batch "
            "DB writes."
        )

    def test_address_bulk_update_fields_declared(self):
        # Explicit field list is required for bulk_update; should be a
        # module-level constant so callers can verify scope.
        assert "ADDRESS_BULK_UPDATE_FIELDS" in _CODE, (
            "Expected ADDRESS_BULK_UPDATE_FIELDS module constant naming "
            "the explicit field set for bulk_update (M2/SW#146)."
        )


class TestM3NoFullMaterialization(SimpleTestCase):
    """M3: batch_input and address_map must not be built in a single pass
    before geocode_batch_chunked is called. Must stream via chunks.
    """

    def test_uses_yield_chunks_helper(self):
        assert "_yield_chunks" in _CODE, (
            "M3/SW#147 fix expected a _yield_chunks helper that streams "
            "addresses through the geocoder in O(chunk_size) memory."
        )

    def test_yield_chunks_is_a_generator(self):
        # Confirm the helper exists as a def + uses `yield`.
        assert "def _yield_chunks" in _CODE
        # Find the function body and confirm `yield` appears inside it.
        match = re.search(
            r"def _yield_chunks\([^)]*\):\s*\n(.*?)(?=\ndef |\Z)",
            _CODE,
            re.DOTALL,
        )
        assert match, "could not find _yield_chunks body"
        body = match.group(1)
        assert "yield" in body, (
            "_yield_chunks must yield (generator), not return a list. "
            "Returning a list would defeat M3's memory cap."
        )

    def test_iterator_uses_chunk_size_arg(self):
        # .iterator(chunk_size=...) is the Django ORM way to stream rows
        # without materializing the full queryset in the prefetch cache.
        assert "iterator(chunk_size=" in _CODE, (
            "M3/SW#147 fix expected qs.iterator(chunk_size=batch_size) for "
            "memory-bounded streaming."
        )
