# Template-readiness E / SW#193 — Economic ingest (design)

**Status:** Design v1. Awaiting maintainer answers on four open questions.

**Parent:** SW#189 (template-readiness initiative).
**Blocked by:** B (#190, done after #206).
**Partially blocked by:** C (#191) — `cbsa` needed for BLS Phase 2; `zcta` needed for IRS SOI Phase 1.

## Goal

Land a `socialwarehouse/economic/` package covering BLS QCEW (employment + wages, county / MSA) and IRS SOI (tax statistics, by ZCTA). After E ships, an analyst can ask:

- "What was Q3 2024 employment in Cook County, Illinois (FIPS 17031)?"
- "Median AGI by ZCTA for state of California in tax year 2022?"
- "How did average weekly wages in MSA 16980 (Chicago-Naperville-Elgin) change between 2019 and 2024?"

## Architecture sketch

```
socialwarehouse/economic/
    __init__.py
    models/
        __init__.py
        bls_qcew.py            # BLSQCEWAggregate, BLSQCEWIndustry (NAICS catalog)
        irs_soi.py             # IRSSOIAggregate, IRSSOIIncomeBucket
    management/
        commands/
            load_qcew.py       # python manage.py load_qcew --vintage 2024Q3 --state 06
            load_irs_soi.py    # python manage.py load_irs_soi --vintage 2022 --state 06
    services/
        bls_api.py             # thin client (BLS QCEW open data, no API key needed for files)
        irs_soi_files.py       # downloads + parses IRS SOI ZIP CSV files
    migrations/
        0001_initial.py
```

## Models (Phase 1 sketch)

### BLSQCEWAggregate

```python
class BLSQCEWAggregate(models.Model):
    vintage = models.ForeignKey("sw_geo.Vintage", on_delete=models.CASCADE, limit_choices_to={"kind": "bls-qcew"})
    boundary_type = models.CharField(max_length=30, db_index=True)  # "county" or "cbsa"
    geoid = models.CharField(max_length=20, db_index=True)
    ownership_code = models.CharField(max_length=10)               # private / state / local / federal / total
    industry_code = models.CharField(max_length=20)                # NAICS, with "10" = total
    avg_monthly_employment = models.PositiveIntegerField(null=True, blank=True)
    total_quarterly_wages = models.BigIntegerField(null=True, blank=True)  # in dollars
    avg_weekly_wage = models.PositiveIntegerField(null=True, blank=True)
    establishment_count = models.PositiveIntegerField(null=True, blank=True)
    class Meta:
        unique_together = [["vintage", "boundary_type", "geoid", "ownership_code", "industry_code"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
            models.Index(fields=["vintage", "industry_code"]),
        ]
```

### IRSSOIAggregate

```python
class IRSSOIAggregate(models.Model):
    vintage = models.ForeignKey("sw_geo.Vintage", on_delete=models.CASCADE)  # bea-regional or a new irs-soi kind
    boundary_type = models.CharField(max_length=30, default="zcta")  # always zcta for SOI
    geoid = models.CharField(max_length=5)                            # ZCTA = 5-digit
    agi_bin = models.ForeignKey("IRSSOIIncomeBucket", on_delete=models.CASCADE)
    return_count = models.PositiveIntegerField(null=True, blank=True)
    taxable_income_total = models.BigIntegerField(null=True, blank=True)
    federal_tax_total = models.BigIntegerField(null=True, blank=True)
    # ... ~20 more aggregate columns per SOI release
    class Meta:
        unique_together = [["vintage", "geoid", "agi_bin"]]
        indexes = [
            models.Index(fields=["geoid", "vintage"]),
        ]
```

## Phasing

- **Phase 1:** BLS QCEW at county level (already a supported boundary type). Ships `BLSQCEWAggregate` + `BLSQCEWIndustry` (NAICS catalog) + `load_qcew --state X --vintage YYYYQQ`.
- **Phase 2:** BLS QCEW at CBSA level. Depends on C's `cbsa` boundary type.
- **Phase 3:** IRS SOI by ZCTA. Depends on C's `zcta` boundary type + Q4 below (new vintage kind for SOI cadence?).

## Four open questions for the maintainer

### Q1. NAICS depth — full or 2-digit?

NAICS codes go 2 → 6 digits (sector → industry). QCEW publishes at all levels. Three options:
- (a) **2-digit (sector) only.** ~20 codes per geography. Small table, coarse granularity.
- (b) **All depths.** Per release, ~hundreds of rows per geography. Big table, full granularity.
- (c) **Configurable** — `load_qcew --naics-depth=2` defaults to 2-digit; users can opt into deeper.

**Recommendation: (c).** Default to 2-digit; deeper on opt-in. Most analyst queries are sector-level; deep loads are big and infrequent.

### Q2. SOI vintage shape — reuse `bea-regional` (annual) or new `irs-soi` kind?

IRS SOI is published annually with a ~2-year lag (2022 data released late 2024). Two options:
- (a) **Reuse `bea-regional`** vintage kind. They're both annual; semantically slightly different but mechanically the same.
- (b) **Add a new `irs-soi` Vintage kind.** Faithful to source semantics. One more kind in `KIND_CHOICES`.

**Recommendation: (b).** Adding a kind is cheap (one row in KIND_CHOICES + a subclass model + migration); reusing creates a long-term confusion ("why is this IRS row under bea-regional?").

### Q3. IRS SOI income-bucket model — fixture or hardcoded enum?

IRS SOI publishes per-bucket aggregates: ~6 buckets ($0-$25K, $25-$50K, ..., $200K+). The bucket boundaries change occasionally. Two options:
- (a) **`IRSSOIIncomeBucket` model + fixture per vintage.** Versionable; if buckets change between vintages the model handles it cleanly.
- (b) **Hardcoded Python enum.** Simpler; brittle if buckets change.

**Recommendation: (a).** Vintage-aware buckets are the kind of detail that's tedious to fix later. Pay the schema cost now.

### Q4. BLS API key needed?

BLS QCEW data is downloadable as ZIP files without an API key. The `bls.gov/cew` open data files contain the same data the API serves. The API offers convenience + rate-limit-aware pagination. Two options:
- (a) **Files only.** No key; works offline-after-download. Ingest re-downloads each quarter.
- (b) **API with key.** Friendlier for incremental loads; key required.

**Recommendation: (a).** No-key path is more template-friendly (template users don't have to register). API path can be added as an opt-in later.

## Out of scope

- BEA regional (separate sub-ticket if needed).
- FCC broadband (Form 477 / BDC).
- Commercial economic data (Moody's, Wharton, etc.).

## Sequencing

- This PR (design v1) → maintainer Q1-Q4 → Phase 1 implementation (county-level QCEW) → Phase 2 (MSA-level QCEW after C ships `cbsa`) → Phase 3 (IRS SOI after C ships `zcta` and Q2 decision lands).

## References

- Parent: SW#189
- B PR #2: #206 (Vintage canonical)
- C design: #207 (zcta + cbsa boundary types come from here)
- BLS QCEW open data: bls.gov/cew/downloadable-data-files.htm
- IRS SOI: irs.gov/statistics/soi-tax-stats-individual-income-tax-statistics-zip-code-data-soi
