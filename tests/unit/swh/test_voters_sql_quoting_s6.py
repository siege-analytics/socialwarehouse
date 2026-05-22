"""Regression test for S6 (SW#136): swh/voters.py validates schema
and table_name as bare ASCII identifiers and quotes them in raw DDL.

Tests the _validate_identifier helper directly — load_voter_file's
end-to-end behavior is exercised by the existing S3 test
(test_voters_lock_swap.py).
"""

from django.test import SimpleTestCase

from swh.voters._legacy_raw import _validate_identifier


class TestValidateIdentifier(SimpleTestCase):

    def test_simple_identifier_accepted_and_quoted(self):
        assert _validate_identifier("voters_tx", "table_name") == '"voters_tx"'

    def test_leading_underscore_accepted(self):
        assert _validate_identifier("_staging_x_abc12345", "staging_table") == '"_staging_x_abc12345"'

    def test_mixed_case_preserved_in_quotes(self):
        assert _validate_identifier("PublicSchema", "schema") == '"PublicSchema"'

    def test_digits_in_middle_accepted(self):
        assert _validate_identifier("voters2024", "table_name") == '"voters2024"'

    def test_leading_digit_rejected(self):
        with self.assertRaises(ValueError):
            _validate_identifier("1voters", "table_name")

    def test_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            _validate_identifier("voters-tx", "table_name")

    def test_dot_rejected_prevents_schema_smuggling(self):
        # The whole point: if someone passed "public.users" as a table
        # name it would smuggle a schema-qualified reference. The
        # validator must reject this even though it "looks like" valid
        # SQL.
        with self.assertRaises(ValueError):
            _validate_identifier("public.users", "table_name")

    def test_space_rejected(self):
        with self.assertRaises(ValueError):
            _validate_identifier("vot ers", "table_name")

    def test_quote_rejected_prevents_injection(self):
        with self.assertRaises(ValueError):
            _validate_identifier('vot"ers', "table_name")

    def test_semicolon_rejected_prevents_statement_break(self):
        with self.assertRaises(ValueError):
            _validate_identifier("vot;drop", "table_name")

    def test_empty_string_rejected(self):
        with self.assertRaises(ValueError):
            _validate_identifier("", "table_name")

    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            _validate_identifier(None, "table_name")  # type: ignore[arg-type]

    def test_error_message_names_kind(self):
        with self.assertRaises(ValueError) as cm:
            _validate_identifier("bad-name", "schema")
        assert "schema" in str(cm.exception)
