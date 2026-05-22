"""Tests for ``swh.analysis.fec.build_graph.entity_type_to_label``.

The pre-modernization (SW#34) implementation was a broken ``match``
statement with no ``return`` / no assignment in any case arm, so the
function silently returned ``None`` for every input. That made the
``itoth`` edges' ``dst`` end up as ``":<OTHER_ID>"`` (no entity-label
prefix), which corrupts the graph topology silently.

These tests pin the corrected behavior and serve as the regression
fence so the broken-``match`` shape can't reintroduce.
"""

from __future__ import annotations

import pytest

from swh.analysis.fec.build_graph import (
    ENTITY_TYPE_TO_LABEL,
    entity_type_to_label,
)


class TestEntityTypeToLabelKnownCodes:
    """Each FEC ENTITY_TP code in the lookup table resolves to a non-empty
    label string."""

    @pytest.mark.parametrize("code,expected", [
        ("CAN", "Candidate"),
        ("CCM", "Committee"),
        ("COM", "Committee"),
        ("PAC", "Committee"),
        ("PTY", "Committee"),
    ])
    def test_known_code_resolves(self, code, expected):
        assert entity_type_to_label(code) == expected


class TestEntityTypeToLabelUnknown:
    """Unknown / null inputs return the empty string (not None)."""

    def test_unknown_code_returns_empty(self):
        assert entity_type_to_label("XXX") == ""

    def test_none_returns_empty(self):
        assert entity_type_to_label(None) == ""

    def test_empty_string_returns_empty(self):
        assert entity_type_to_label("") == ""


class TestSW34RegressionFence:
    """Direct fence on the SW#34 bug shape: pre-modernization the
    function always returned ``None``; today it returns a string.

    This test name + assertion exists so any future refactor that
    re-introduces the broken ``match`` shape fails noisily here rather
    than silently corrupting the ``itoth`` edges in production."""

    def test_known_input_does_not_return_none(self):
        # Pre-modernization, this would have been None for every input
        # including known codes. The bug was silent because the calling
        # code did `concat(label, ":", OTHER_ID)` and None concat'd
        # in SQL yields an empty / null result.
        result = entity_type_to_label("CAN")
        assert result is not None
        assert result == "Candidate"

    def test_lookup_table_is_non_empty(self):
        # Belt and suspenders: if the lookup table is emptied at some
        # future point, every known input falls back to "". The test
        # above would still pass IF "CAN" were removed from the table.
        # This test guards against that.
        assert len(ENTITY_TYPE_TO_LABEL) >= 5
        assert "CAN" in ENTITY_TYPE_TO_LABEL
        assert ENTITY_TYPE_TO_LABEL["CAN"] == "Candidate"
