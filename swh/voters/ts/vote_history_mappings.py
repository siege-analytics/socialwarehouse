"""
TS vote-history column-pattern parsing.

TS encodes vote participation as per-cycle columns:
- vb.vf_g_<year>          general participation (truthy = voted)
- vb.vf_p_<year>          primary participation (truthy = voted)
- vb.vf_g_method_<year>   method code for general (I/A/M/E/P/...)
- vb.vf_p_method_<year>   method code for primary

Election dates: TS ships year-only granularity. We use canonical defaults
per election_type. Operators with state-specific primary dates should
extend this map; the default is a documented approximation.
"""

from datetime import date


# Election-type prefix -> (election_type label, default month-day).
# Year is parsed from the column name; combined with month-day to get a Date.
ELECTION_TYPE_PREFIXES: dict[str, tuple[str, tuple[int, int]]] = {
    "vb.vf_g_method_": ("general", (11, 5)),    # method columns are paired with g_<year>
    "vb.vf_p_method_": ("primary", (3, 15)),
    "vb.vf_g_": ("general", (11, 5)),
    "vb.vf_p_": ("primary", (3, 15)),
}


# TS method-code -> canonical voted_method.
# Source: TS data dictionary, vote-method codes for vf_*_method_* columns.
METHOD_CODES: dict[str, str] = {
    "I": "in_person",
    "A": "absentee",
    "M": "mail",
    "E": "early",
    "P": "provisional",
    "": "unknown",
}


TRUTHY_VOTED = {"1", "Y", "y", "T", "t", "TRUE", "true", "True"}


def parse_column(column_name: str) -> tuple[str, int, bool] | None:
    """Resolve a TS column name to (election_type, year, is_method_column).

    Returns None if the column is not a vote-history column. Method
    columns return is_method_column=True; participation columns return
    False.
    """
    # Check method prefixes first since they're more specific
    # (vb.vf_g_method_ matches before vb.vf_g_).
    for prefix, (etype, _md) in ELECTION_TYPE_PREFIXES.items():
        if column_name.startswith(prefix):
            year_part = column_name[len(prefix):]
            if year_part.isdigit() and len(year_part) == 4:
                is_method = "_method_" in prefix
                return etype, int(year_part), is_method
    return None


def election_date_for(election_type: str, year: int) -> date:
    """Canonical date for (election_type, year).

    General defaults to Nov 5; primary defaults to Mar 15. Operators
    needing state-accurate primary dates can override at silver-build
    time (follow-on).
    """
    for prefix, (etype, (mm, dd)) in ELECTION_TYPE_PREFIXES.items():
        if etype == election_type:
            return date(year, mm, dd)
    return date(year, 1, 1)  # fallback; shouldn't happen for known types


def canonical_method(code: str) -> str:
    """TS method code -> canonical voted_method string."""
    if code is None:
        return "unknown"
    return METHOD_CODES.get(code.strip(), "unknown")


def is_voted(value) -> bool:
    """Did the voter participate in this election per the TS value?"""
    if value is None:
        return False
    return str(value).strip() in TRUTHY_VOTED


# Vote-frequency category derived from total counts. Bucket boundaries
# documented here for stability; if these change, downstream consumers
# need to know.
def vote_frequency_category(general_count: int, total_count: int) -> str:
    """Derive a coarse engagement bucket from vote counts.

    Buckets:
    - super_voter: 4+ generals voted
    - regular: 2-3 generals voted
    - occasional: 1 general voted
    - non: 0 generals voted (regardless of primary participation)
    """
    if general_count >= 4:
        return "super_voter"
    if general_count >= 2:
        return "regular"
    if general_count >= 1:
        return "occasional"
    return "non"
