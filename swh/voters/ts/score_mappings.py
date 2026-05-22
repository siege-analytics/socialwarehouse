"""
TS score-column -> canonical (score_type, methodology_version) mapping.

The right-hand side is a (score_type, methodology_version_template) tuple
where the template is a Python format string supporting `{cycle}` if the
TS column embeds a cycle year.

Static (non-cycle-aligned) TS scores get an empty cycle placeholder and
take the operator-supplied default methodology version (e.g. 'ts-2024').

The score_type vocabulary aligns with `docs/entities/fact-person-score.md`
registered values. Adding a new TS score means picking the matching
registered score_type or adding a new one to that doc.
"""

# Static scores: methodology version is the importer's default ('ts-<vintage>').
# Format-string here uses {default} which the caller fills in.
_STATIC: dict[str, tuple[str, str]] = {
    "vb.tsmart_partisan_score": ("partisan_score", "{default}"),
    "vb.tsmart_ideology_score": ("ideology_score", "{default}"),
    "vb.tsmart_engagement_score": ("engagement_score", "{default}"),
    "vb.tsmart_persuadability_score": ("persuadability_score", "{default}"),
    "vb.tsmart_climate_score": ("issue_climate", "{default}"),
    "vb.tsmart_abortion_score": ("issue_abortion", "{default}"),
    "vb.tsmart_gun_safety_score": ("issue_gun_safety", "{default}"),
    "vb.tsmart_healthcare_score": ("issue_healthcare", "{default}"),
    "vb.tsmart_economy_score": ("issue_economy", "{default}"),
    "vb.tsmart_immigration_score": ("issue_immigration", "{default}"),
}

# Cycle-aligned scores: methodology version embeds the cycle year extracted
# from the TS column name. The score_type strips the year so it's stable
# across cycles. The pattern is `vb.tsmart_turnout_score_<scope>_<year>`.
# The cycle key in the format string is filled from the matched year.
_CYCLE_TURNOUT_GENERAL = ("turnout_propensity_general", "ts-{cycle}")
_CYCLE_TURNOUT_PRIMARY = ("turnout_propensity_primary", "ts-{cycle}")

# Cycle patterns are matched at runtime; this dict declares the prefix
# stem -> (score_type, methodology_template) mapping. The caller parses
# the trailing year.
CYCLE_PREFIXES: dict[str, tuple[str, str]] = {
    "vb.tsmart_turnout_score_general_": _CYCLE_TURNOUT_GENERAL,
    "vb.tsmart_turnout_score_primary_": _CYCLE_TURNOUT_PRIMARY,
}


def lookup(column_name: str, default_methodology: str) -> tuple[str, str] | None:
    """Resolve a TS column name to (score_type, methodology_version).

    Returns None if the column is not a known score column.

    Args:
        column_name: Full TS column name (with `vb.` prefix).
        default_methodology: Methodology label for static (non-cycle)
            scores. Typical value: "ts-2024".
    """
    if column_name in _STATIC:
        score_type, template = _STATIC[column_name]
        return score_type, template.format(default=default_methodology)
    for prefix, (score_type, template) in CYCLE_PREFIXES.items():
        if column_name.startswith(prefix):
            cycle = column_name[len(prefix):]
            if cycle.isdigit() and len(cycle) == 4:
                return score_type, template.format(cycle=cycle)
    return None


def known_score_columns(default_methodology: str = "ts-2024") -> set[str]:
    """All TS column names that map to a canonical score_type.

    Excludes cycle-aligned columns (those are matched by prefix at
    runtime since the year is variable). For introspection / docs.
    """
    return set(_STATIC.keys())
