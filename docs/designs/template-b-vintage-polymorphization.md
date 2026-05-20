# Template-readiness B / SW#190 — Vintage model polymorphization (design)

**Status:** Design v2 (2026-05-19). Maintainer answered Q2 + Q3; lean toward Shape A on Q1 + "can be talked into it"; asked Q4 to be elaborated. Re-pitch on shape introduces a third option (Shape A2: Django multi-table inheritance) that splits the difference between v1's A and B.

## Resolved decisions (v2)

### Q2: delete CensusVintageConfig + redo migrations (no proxy)

> "Don't do a proxy, go ahead and delete and redo it. Fresh migrations."

Implementation PR drops `CensusVintageConfig` entirely; all callers migrate to the new `Vintage` API in the same PR. No backwards-compat shim. The audit of `CensusVintageConfig` call sites happens at impl-PR time; the migration scope is bounded by that grep.

### Q3: pre-seed every known vintage, not just census-decadal

> "Why only fill previous Census decade?"

Original v1 wording was misleading. Revised: ship a `seed_known_vintages` management command that pre-populates `Vintage` rows for every known vintage across the four data domains, run in the migration so the table is immediately useful:

- **census-decadal:** 2010, 2020 (and forward as Census drops them).
- **acs-5year:** every endpoint year from 2009-2013 through the latest published. Same for **acs-1year** for places ≥65K.
- **bls-qcew:** every quarter from a reasonable cutoff (2010Q1) to the latest published.
- **bea-regional:** every year from cutoff to latest.
- **nces-school-year:** every school year from cutoff to latest.
- **redistricting-plan:** NOT pre-seeded by this command — those rows come from the existing `assign_boundaries` flow and from SU's `RedistrictingPlan` table; the vintage row is created on first reference.

Pros: immediately useful Vintage table after the migration. Ingest commands (sub-issues D-F) don't need to bootstrap their own vintage rows.

Cons: the seed list is "as of when the migration was written" — new vintages published later require re-running `seed_known_vintages`. Command is idempotent; re-running adds only new rows.

## The shape re-pitch: Shape A2 (Django multi-table inheritance)

> "Funny you say B, I lean A for type safety. Can be talked into it."

Reconsidering v1's recommendation honestly: the A-vs-B framing missed a third option that Django supports natively — **multi-table inheritance**. It gives both type safety per subclass AND a single FK target for ABP. Here's how it differs from v1's options:

### Shape A2: concrete-parent multi-table inheritance

```python
class Vintage(models.Model):
    """Concrete parent. All vintage subtypes inherit from this.
    Django gives each subclass its own table PLUS a 1:1 FK to this
    parent. Queries against Vintage return parent rows; downcasting
    via .acsvintage / .blsqcewvintage / .censusdecadalvintage etc.
    """
    name = models.CharField(max_length=100, db_index=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    kind = models.CharField(max_length=30, db_index=True)  # discriminator for fast lookups
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["kind", "effective_to"]),
            models.Index(fields=["effective_from", "effective_to"]),
        ]


class CensusDecadalVintage(Vintage):
    decade = models.PositiveSmallIntegerField(unique=True)

    def save(self, *args, **kwargs):
        self.kind = "census-decadal"
        super().save(*args, **kwargs)


class ACSVintage(Vintage):
    start_year = models.PositiveSmallIntegerField()
    end_year = models.PositiveSmallIntegerField()
    span_years = models.PositiveSmallIntegerField(choices=[(1, "1-year"), (5, "5-year")])

    class Meta:
        unique_together = [["start_year", "end_year", "span_years"]]

    def save(self, *args, **kwargs):
        self.kind = "acs"
        super().save(*args, **kwargs)


class BLSQCEWVintage(Vintage):
    year = models.PositiveSmallIntegerField()
    quarter = models.PositiveSmallIntegerField(choices=[(1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4")])

    class Meta:
        unique_together = [["year", "quarter"]]

    def save(self, *args, **kwargs):
        self.kind = "bls-qcew"
        super().save(*args, **kwargs)


# ... etc for BEAVintage, NCESSchoolYearVintage, RedistrictingPlanVintage.


# ABP's FK targets the parent.
class AddressBoundaryPeriod(models.Model):
    vintage = models.ForeignKey("sw_geo.Vintage", on_delete=models.CASCADE, ...)
```

### How A2 splits the v1 trade-off

| Concern | v1 Shape A (abstract base + GFK) | v1 Shape B (single table + JSON) | **Shape A2 (multi-table inheritance)** |
|---|---|---|---|
| Type safety per kind | strong (subclass has typed fields) | weak (JSON dict per kind) | **strong** (subclass tables have typed fields) |
| ABP FK target | GFK or multi-FK | single FK | **single FK to Vintage parent** |
| Cross-kind queries | hard (no parent table) | easy (one table) | **easy (parent table)** |
| F11 helper cost (reads effective_from/to) | per-subclass query | one column read | **one column read on parent** |
| Adding a new kind | new model + migration | append to KIND_CHOICES | new subclass + migration |
| Schema cost | one table per kind | one table total | **one table per kind + parent table** |
| Subtype access | walk through GFK or per-kind reverse | unpack JSON details | **downcast via .acsvintage etc.** |
| Migration shape | per-kind initial migration | single migration | parent + per-kind migrations |

A2 is essentially v1 Shape A but using Django's concrete-parent inheritance instead of abstract + GFK. Django handles the parent / child plumbing; the parent table is queryable directly.

### Revised recommendation

**Shape A2.** Reasons it matches the user's "lean A for type safety":
- Type safety per subclass is preserved (the user's stated preference).
- ABP FKs the parent — clean, no GFK awkwardness, single column.
- F11 helpers read flat `Vintage.effective_from / effective_to` columns on the parent table (one query, no downcast).
- Per-kind subclasses carry their type-safe extras (`ACSVintage.span_years`, `BLSQCEWVintage.quarter`, etc.) without polluting the parent.
- Adding a new kind is a per-kind migration — same as v1 Shape A.

The trade-off vs v1 Shape A pure form: Django creates a parent table + child tables (one row in each per vintage). Modest schema cost; pays for itself by making cross-kind queries trivial.

The trade-off vs v1 Shape B: each new kind is a code change (new subclass) plus a migration. Not a config change. That's appropriate for vintage kinds — they correspond to real data sources with bespoke fields; "just add a string to KIND_CHOICES" doesn't capture that ACSVintage needs `span_years` and BLSQCEWVintage needs `quarter`.

If you push back on A2 specifically (e.g., "we don't want Django's multi-table inheritance because of historical performance concerns"), the fallback is v1 Shape A with GFK. Shape B is the "minimal-surface" answer but doesn't match the type-safety priority you named.

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

### Q4. Migration window — hard cutover only (Q2 ruled out shims) (elaboration)

User answered Q2: "Don't do a proxy, go ahead and delete and redo it. Fresh migrations." That means the migration window question is no longer "shim vs hard cutover" — it's "what does the hard cutover look like, exactly?"

Three sub-options for the hard-cutover shape, each with concrete shapes:

#### (Q4-i) Single-PR hard cutover

**Shape:** one PR that:
1. Adds the `Vintage` parent + per-kind subclass models + migrations (CreateModel for each).
2. Adds the `seed_known_vintages` management command + a data migration that runs it.
3. Drops `CensusVintageConfig` (RemoveModel).
4. Adds an ABP migration that retargets the `vintage` FK to point at the new `Vintage` parent.
5. Adds a data migration that walks ABP rows, looks up the corresponding new `CensusDecadalVintage` row by decade, and updates ABP's `vintage_id`.
6. Updates every caller of `CensusVintageConfig.for_year(...)` and `CensusVintageConfig.objects.*` to the new `Vintage` API in the same PR.

**Pros:**
- Atomic. Either the whole migration lands or none of it does.
- No partial state where some code uses old, some uses new.
- One review pass.

**Cons:**
- Big PR. Touches model definitions, migrations, data migration, every caller, F11 step-2 helpers (which currently reference `vintage.effective_start` integer-year), tests.
- Failure mode: if any migration fails mid-deploy, rollback is complex.
- Hard to review in chunks; reviewer either reads the whole thing or none of it.

#### (Q4-ii) Two-PR hard cutover (model + migrations first, callers second)

**Shape:**
- PR #1: ship `Vintage` model + subclasses + `seed_known_vintages` + migrations. `CensusVintageConfig` stays for now. ABP's FK stays pointed at `CensusVintageConfig`. Existing code keeps working.
- PR #2 (lands later): drops `CensusVintageConfig`, retargets ABP's FK, migrates callers.

**Pros:**
- PR #1 is small + risk-free (additive only).
- PR #2 can be planned + reviewed against the now-existing Vintage table.
- Rollback story is cleaner: if PR #2 breaks, revert it without losing PR #1's model.

**Cons:**
- Two PRs to coordinate.
- PR #1 ships a Vintage table that's unused by ABP — looks weird in isolation.
- Brief window where both tables exist; can confuse readers.

#### (Q4-iii) Three-PR sequenced hard cutover

**Shape:**
- PR #1: ship `Vintage` model + subclasses + `seed_known_vintages` + migrations. Same as Q4-ii PR #1.
- PR #2: add a new `vintage_new` FK on ABP pointing at the new Vintage parent; data-migrate to populate it from `vintage` (the old FK); existing code keeps reading `vintage` (the old FK).
- PR #3: switch all caller code to read `vintage_new`; in the same PR, rename `vintage_new` → `vintage` and drop the old FK + `CensusVintageConfig`.

**Pros:**
- Each PR is small and reviewable.
- Each landed state is functional.
- The intermediate "vintage_new" naming is awkward but bounded — only present between PR #2 and PR #3.

**Cons:**
- Three PRs of coordination overhead.
- The rename in PR #3 is fiddly (Django migration for FK rename + caller code update).
- For a one-team project, this is over-engineered.

#### Recommendation

**Q4-ii (two-PR hard cutover).** Reasoning:
- Q4-i (single PR) is too big to review confidently for a central model. The data migration alone is the kind of change that wants its own review pass.
- Q4-iii (three PRs) is excessive for the actual blast radius; the `vintage_new`-then-rename dance is more ceremony than safety.
- Q4-ii hits the sweet spot: PR #1 is risk-free (additive Vintage + seed); PR #2 is the actual cutover and can be reviewed against the now-existing Vintage table. Total surface area is about the same as Q4-i, but split into reviewable pieces.

If you'd rather go Q4-i (one PR), I can ship it; the recommendation is "split into two if review bandwidth allows it."

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
