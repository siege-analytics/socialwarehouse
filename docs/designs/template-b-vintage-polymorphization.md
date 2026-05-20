# Template-readiness B / SW#190 — Vintage model polymorphization (design)

**Status:** Design v1. No code. Awaiting maintainer answers to four
questions (named below) before the implementation PR opens.

**Parent:** SW#189 (template-readiness initiative).
**Blocks:** sub-issues C through F (each ingest path needs the polymorphic
vintage to exist before its rows are well-shaped).
**Blocked by:** F11 finish — step 2b design SW#197, then step 3.

## Goal

Replace the single `CensusVintageConfig` table with a polymorphic
**Vintage** concept that accommodates the temporal shapes of every
data domain the template ships:

| Source | Vintage shape |
|---|---|
| Decennial Census | Every 10 years (`2010`, `2020`, ...) |
| ACS 5-year | Rolling 5-year endpoint (`2019-2023`) |
| ACS 1-year | Single year, places ≥65K population |
| BLS QCEW | Quarterly (`2024Q3`) |
| BEA regional | Annual (`2024`) |
| Redistricting plan | Irregular, court-driven (start + end dates) |
| NCES school district | Annual (school year `2023-24`) |

After this lands:
- `AddressBoundaryPeriod.vintage` can FK to any kind of vintage, not just
  `CensusVintageConfig`.
- F11 helpers (`boundary_timeline`, `boundaries_on`, ...) derive effective
  ranges from whichever vintage subtype is linked.
- Adding a new vintage kind is a model-add + migration, not a core-helper
  rewrite.

## Two candidate shapes

### Shape A: Abstract base + concrete subclasses

```python
class Vintage(models.Model):
    """Abstract base for all temporal-period concepts."""
    name = models.CharField(max_length=100, db_index=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    @property
    def kind(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"


class CensusDecadalVintage(Vintage):
    decade = models.PositiveSmallIntegerField(unique=True)
    @property
    def kind(self): return "census-decadal"


class ACSVintage(Vintage):
    start_year = models.PositiveSmallIntegerField()
    end_year = models.PositiveSmallIntegerField()
    span_years = models.PositiveSmallIntegerField(choices=[(1, "1-year"), (5, "5-year")])
    @property
    def kind(self): return "acs"


class BLSQCEWVintage(Vintage):
    year = models.PositiveSmallIntegerField()
    quarter = models.PositiveSmallIntegerField(choices=[(1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4")])
    @property
    def kind(self): return "bls-qcew"


# ... etc.
```

ABP's `vintage` FK can't directly target an abstract base. Options:
- **A1.** Multiple FKs on ABP (`vintage_census_decadal`, `vintage_acs`, ...), with a validation that exactly one is set per row. Awkward.
- **A2.** Django GenericForeignKey via `ContentType`. Idiomatic Django for this case. ORM-friendly; queries can pivot through the GFK.
- **A3.** A separate `BoundaryAssignmentVintage` table (concrete) that links to one of the vintage subtypes (via GFK or per-kind FKs), and ABP FKs to that. One level of indirection but cleaner if multiple ABP-like tables need to reference the same vintage concept.

Pros: type-safe per-subclass attributes. The `span_years` choice on `ACSVintage` doesn't pollute the `CensusDecadalVintage` schema.
Cons: GFK queries are a little awkward; ORM users need to use `.vintage_content_type` + `.vintage_object_id` patterns or per-kind reverse accessors.

### Shape B: Single table + discriminator + JSON details

```python
class Vintage(models.Model):
    """Single-table vintage with a kind discriminator."""
    KIND_CHOICES = [
        ("census-decadal", "Decennial Census"),
        ("acs", "ACS"),
        ("bls-qcew", "BLS QCEW"),
        ("bea-regional", "BEA Regional"),
        ("nces-school-year", "NCES School Year"),
        ("redistricting-plan", "Redistricting Plan"),
    ]
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, db_index=True)
    name = models.CharField(max_length=100, db_index=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["kind", "name"]]
```

ABP's `vintage` is a single FK. Subtype-specific fields go in `details`
JSON (e.g. `{"decade": 2020}`, `{"start_year": 2019, "end_year": 2023, "span_years": 5}`,
`{"year": 2024, "quarter": 3}`).

Pros: single FK; simple cross-kind queries; easy to add a new kind
(no new model / migration). Effective-range filtering uses the flat
`effective_from` / `effective_to` columns and works across kinds.
Cons: subtype-specific fields aren't type-safe; JSON details mean
each kind's reader needs to know which keys to pull.

## Recommendation

**Shape B.** Reasons:
- F11's read helpers only need `effective_from` / `effective_to` and a
  display name. Those are flat columns under shape B; under shape A
  the helpers need to walk through GFK to find them per subtype.
- Adding a new kind in the template's lifetime is a config change
  (add to `KIND_CHOICES`), not a schema migration + model class
  addition.
- The "kind-specific fields aren't type-safe" downside is real but
  scoped to the per-kind ingest code (which knows its own kind
  anyway). Helper code that's kind-agnostic doesn't care.

Shape A's type-safety wins matter most when many call sites read
kind-specific fields. Today the only kind-specific reader is the
ingest path per domain (D, E, F sub-issues), each of which reads its
own kind only. Type-safety per kind is a small win there; the
cross-kind ergonomic win from shape B is larger.

## Migration plan

`CensusVintageConfig` becomes `Vintage` rows with `kind="census-decadal"`
and `details={"decade": ..., "effective_start": ..., "effective_end": ...}`.

Migration steps:
1. **Data migration**: copy each `CensusVintageConfig` row into a new
   `Vintage` row with `kind="census-decadal"`, populate `details` from
   the old columns, copy `effective_start` / `effective_end` to
   `effective_from` / `effective_to` (decade-year → calendar-date:
   `date(year, 1, 1)` and `date(year, 12, 31)` respectively).
2. **Schema migration**: ABP's `vintage` FK target changes from
   `CensusVintageConfig` to `Vintage`. Run an UPDATE that resolves
   each ABP's old `vintage_id` → the new `Vintage.id` via the data
   migration's mapping.
3. **Drop `CensusVintageConfig`**: deprecated in favor of `Vintage`
   with `kind="census-decadal"`. Existing call sites
   (`CensusVintageConfig.for_year(year)`) get a thin wrapper / shim
   that proxies to `Vintage.objects.filter(kind="census-decadal", ...)`.
4. **F11 helpers**: `boundary_timeline` / `boundaries_on` read
   `vintage.effective_from / .effective_to` directly — no kind-aware
   branching needed for the temporal-range path.

## Four open questions for the maintainer

### Q1. Shape A or Shape B?

Recommended: **B** (single table + discriminator). See "Recommendation"
above for the trade-off. Shape A is the right answer if cross-kind
type-safety matters more than cross-kind queryability.

### Q2. Rename or keep `CensusVintageConfig`?

After this lands, `CensusVintageConfig` is conceptually a Vintage with
`kind="census-decadal"`. Three options:
- (a) Rename it to `CensusDecadalVintage` and keep the dedicated table
  (shape A's structure). Inconsistent with Shape B's "single table"
  premise.
- (b) Delete it; replace all callers with `Vintage.objects.filter(kind=...)`.
- (c) Keep it as a thin proxy class (`class CensusVintageConfig(Vintage): ...`
  with a `kind="census-decadal"` default, possibly a `proxy=True` Meta).
  Preserves API; lets existing call sites work unchanged.

Recommended: **(c) proxy class.** Lowest blast radius.

### Q3. What's the minimum set of vintage kinds to ship with this PR?

The KIND_CHOICES list above has six entries. Do we ship all six in
this PR or only the kinds that have ingest paths today (just
`census-decadal` and `redistricting-plan`, with the others added by
sub-issues D-F as they need them)?

Recommended: **ship the kind catalog (all six choices) but only
backfill / migrate the kinds that have existing rows
(`census-decadal`)**. Adding a new kind later is then a no-op (the
choice already exists); per-kind ingest sub-tickets just start
writing rows.

### Q4. Migration window — hard cutover or backwards-compat shims?

The `CensusVintageConfig.for_year(...)` manager is called in several
SW paths. Three options:
- (a) **Hard migration**: rename callers in the same PR. Bigger PR
  surface; cleaner end state.
- (b) **Backwards-compat shim**: Q2's option (c) (proxy class) keeps
  the old API working. PR ships small; callers migrate at their own
  pace; eventually the shim is removed.
- (c) **Hybrid**: shim AND update some callers (the most-trafficked
  ones) in the same PR; defer the rest.

Recommended: **(b)** for the implementation PR; **(a)** as a follow-up
that removes the shim once callers have migrated.

## Risk

- **Migration data loss** if the `CensusVintageConfig` → `Vintage`
  data migration drops rows or misshapes the date conversion. The
  implementation PR should include a fixture-loaded round-trip test
  (load CensusVintageConfig fixture; run migration; assert each
  row's Vintage equivalent has correct kind / details / dates).
- **Hidden callers** of `CensusVintageConfig` that the audit misses.
  A `grep` pass in the implementation PR + the proxy class from Q2-(c)
  means we degrade to "uses the proxy" rather than "breaks."
- **F11 helper changes** if the `vintage.effective_from / .effective_to`
  columns shift name. The helper code already references those names
  per F11 step 2b's design — Shape B's flat columns mean no helper
  changes needed.

## Sequencing

- This PR (design v1): sign-off on Q1-Q4. **← here.**
- Implementation PR: `Vintage` model + migration + data migration +
  ABP FK retarget + proxy class for `CensusVintageConfig` + tests.
- Follow-up tickets (filed after impl lands):
  - C (#191) — boundary catalog expansion (each new boundary type's
    ingest uses the polymorphic vintage).
  - D-F (#192-#194) — per-domain ingest packages, each adding rows of
    their respective vintage kinds.
  - Cleanup follow-up: remove the `CensusVintageConfig` proxy once
    callers have migrated.

## References

- Parent: SW#189 (template-readiness initiative).
- F11 step-2 design (v2.2): `docs/designs/f11-address-temporal-boundary-history.md`.
- F11 step-2b design (this PR's sibling): `docs/designs/f11-step2b-signal-cache-refresh.md`.
- SU#527 / SU#528: the missing-migration bug that surfaced the importance of model-vs-migration verification — same care needed for this PR's data migration.
- Existing vintage model: `socialwarehouse/geo/models/census_vintage.py:14-90`.
- ABP model: `socialwarehouse/geo/models/address_boundary.py:23-180`.
