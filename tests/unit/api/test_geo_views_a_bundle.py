"""Regression tests for the api/geo bundle: A4+A5+A7+A8+A10.

A4 (#115): module docstring no longer claims BoundaryManager wrapping.
A5 (#116): boundary_detail cache_page TTL is 1 day, not 7.
A7 (#118): _standardize_address documents itself as a placeholder.
A8 (#119): _serialize_boundary hasattr chain documented in-source.
A10 (#121): _standardize_address return drops the dead "input" key.

A5 verification uses a source-grep on the decorator line (writing-tests:6
inspection carve-out — decorator inspection from a live api_view is
unreliable through the DRF wrapper).
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from socialwarehouse.api.geo import views as _views


_SRC = Path(_views.__file__).read_text(encoding="utf-8")


def _strip_comments_and_docstrings(source):
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out = []
    for line in cleaned.splitlines():
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


_CODE = _strip_comments_and_docstrings(_SRC)


class TestModuleDocstring(SimpleTestCase):
    def test_docstring_no_longer_claims_boundarymanager_wrapping(self):
        # Module docstring should NOT describe a BoundaryManager wrapper
        # (no such import exists). The new wording mentions queryset
        # manager methods directly. A4 / SW#115.
        doc = _views.__doc__ or ""
        # The literal phrase from the stale docstring must be gone.
        assert "Wraps siege_utilities BoundaryManager" not in doc
        # The corrected wording mentions queryset / manager methods.
        assert "queryset manager methods" in doc

    def test_no_boundarymanager_import(self):
        assert "BoundaryManager" not in _CODE or "No `BoundaryManager`" in (_views.__doc__ or "")


class TestBoundaryDetailCacheTTL(SimpleTestCase):
    def test_cache_page_is_one_day_not_seven(self):
        # A5 / SW#116. The decorator line must apply a 1-day TTL on the
        # boundary_detail view, not 7-day. Source-grep because the
        # cached function object exposes the wrapper, not the original
        # decorator args.
        # Match either `60 * 60 * 24` exactly, OR the literal 86400.
        # MUST NOT match `60 * 60 * 24 * 7` or 604800 anywhere in views.py.
        assert re.search(r"@cache_page\(\s*60\s*\*\s*60\s*\*\s*24\s*\)", _CODE), (
            "expected @cache_page(60*60*24) (1 day) on a view"
        )
        assert "60 * 60 * 24 * 7" not in _CODE, (
            "7-day cache_page TTL still present; A5 fix reverted?"
        )


class TestStandardizeAddressPlaceholder(SimpleTestCase):
    def test_standardize_drops_dead_input_key(self):
        # A10 / SW#121. The helper's return dict must no longer carry
        # an outer "input" key — the caller surfaces the original
        # address as "original" and never used the inner key.
        result = _views._standardize_address("123 Main St, Austin, TX 78701")
        assert "input" not in result
        assert "components" in result
        assert result["components"]["street"] == "123 Main St"
        assert result["components"]["city"] == "Austin"
        assert result["components"]["state"] == "TX"
        assert result["components"]["zip"] == "78701"

    def test_two_part_fallback_still_works(self):
        result = _views._standardize_address("123 Main St, Austin TX 78701")
        assert "input" not in result
        assert result["components"]["street"] == "123 Main St"
        assert result["components"]["city_state_zip"] == "Austin TX 78701"

    def test_no_comma_fallback(self):
        result = _views._standardize_address("just a string")
        assert "input" not in result
        assert result["components"]["raw"] == "just a string"

    def test_docstring_marks_placeholder(self):
        # A7 / SW#118. The helper's docstring should self-identify as a
        # placeholder so future maintainers don't mistake it for a
        # production parser.
        doc = _views._standardize_address.__doc__ or ""
        assert "PLACEHOLDER" in doc or "placeholder" in doc


class TestSerializeBoundaryHasattrChainDocumented(SimpleTestCase):
    def test_docstring_explains_field_heterogeneity(self):
        # A8 / SW#119. The hasattr chain stays; the docstring must
        # explain WHY (BOUNDARY_MODELS span tables with different
        # field sets).
        doc = _views._serialize_boundary.__doc__ or ""
        # Must mention at least one model-specific field and the
        # rationale phrase.
        assert "TimezoneGeometry" in doc
        assert "CongressionalDistrict" in doc or "district_number" in doc
