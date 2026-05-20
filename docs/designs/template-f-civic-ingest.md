# Template-readiness F / SW#194 — Civic ingest (design)

**Status:** Design v1. Awaiting maintainer answers on four open questions.

**Parent:** SW#189 (template-readiness initiative).
**Blocked by:** B (#190, done after #206).
**Partially blocked by:** C (#191) — `school_district` needed for Phase 1; `special_district` needed for Phase 2.

## Goal

Land a `socialwarehouse/civic/` package that ingests school-district enrollment / staffing / funding data from NCES (National Center for Education Statistics) and special-district records from the Census Special Districts file. After F ships:

- "How many K-12 students were enrolled in the Chicago Public Schools (district id 1709930) in 2022-23?"
- "What fire-protection special districts overlap this address?"
- "Federal Title I funding per district for state X in 2023-24?"

## Architecture sketch

```
socialwarehouse/civic/
    __init__.py
    models/
        __init__.py
        nces_school_district.py    # NCESDistrictAggregate
        special_district.py         # SpecialDistrictAttributes (boundary lives in SU)
    management/
        commands/
            load_nces.py            # python manage.py load_nces --vintage 2023-24 --state 06
            load_special_districts.py  # python manage.py load_special_districts --vintage 2020 --state 06
    services/
        nces_files.py               # downloads + parses NCES CCD / EDGE files
        census_special_districts.py # parses Census Special Districts shapefile + attributes
    migrations/
        0001_initial.py
```

## Models

### NCESDistrictAggregate

Per-district per-school-year aggregates. Boundary geometry + district identifiers live upstream in siege_utilities (delivered by C); F adds the warehouse-side aggregate counts.

```python
class NCESDistrictAggregate(models.Model):
    vintage = models.ForeignKey("sw_geo.Vintage", on_delete=models.CASCADE, limit_choices_to={"kind": "nces-school-year"})
    boundary_type = models.CharField(max_length=30, default="school_district")
    geoid = models.CharField(max_length=20)   # NCES LEAID
    district_type = models.CharField(max_length=20)  # unified / elementary / secondary
    enrollment_total = models.PositiveIntegerField(null=True, blank=True)
    teachers_fte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    revenue_federal = models.BigIntegerField(null=True, blank=True)
    revenue_state = models.BigIntegerField(null=True, blank=True)
    revenue_local = models.BigIntegerField(null=True, blank=True)
    title_i_eligible = models.BooleanField(null=True, blank=True)
    free_lunch_eligible_count = models.PositiveIntegerField(null=True, blank=True)
    class Meta:
        unique_together = [["vintage", "geoid"]]
        indexes = [
            models.Index(fields=["boundary_type", "geoid", "vintage"]),
        ]
```

### SpecialDistrictAttributes

Per-district attributes for Census Special Districts. The boundary itself lives in SU (delivered by C with the `special_district` boundary type). F adds attributes like the district's specific function (fire / water / hospital / library / ...), governing body, source URL, etc.

```python
class SpecialDistrictAttributes(models.Model):
    vintage = models.ForeignKey("sw_geo.Vintage", on_delete=models.CASCADE)  # census-decadal
    geoid = models.CharField(max_length=20)
    district_function = models.CharField(  # the sub-kind from C's Q2 decision
        max_length=30,
        choices=[
            ("fire", "Fire Protection"),
            ("water", "Water Supply"),
            ("hospital", "Hospital"),
            ("library", "Library"),
            ("cemetery", "Cemetery"),
            ("mosquito", "Mosquito Abatement"),
            ("other", "Other"),
        ],
    )
    governing_body = models.CharField(max_length=255, blank=True, default="")
    annual_revenue = models.BigIntegerField(null=True, blank=True)
    class Meta:
        unique_together = [["vintage", "geoid"]]
```

## Phasing

- **Phase 1:** NCES school districts. Depends on C shipping `school_district` boundary type. Ships `NCESDistrictAggregate` + `load_nces`.
- **Phase 2:** Special districts. Depends on C shipping `special_district` + Q2 sub-typing decision. Ships `SpecialDistrictAttributes` + `load_special_districts`.

## Four open questions for the maintainer

### Q1. NCES data source — CCD or EDGE?

NCES publishes both:
- **CCD (Common Core of Data):** the per-district aggregates table (enrollment, staff, finance). What this ticket primarily targets.
- **EDGE (Education Demographic and Geographic Estimates):** boundary geometries + Census-derived demographic estimates for districts.

C ships the boundary side (EDGE-style geometries). F ships the attribute side (CCD-style aggregates). They're complementary. Two options:
- (a) **CCD only for F's first ingest.** Boundary side covered by C.
- (b) **CCD + EDGE demographic estimates** (the "school-age population in this district" tables).

**Recommendation: (a).** EDGE demographic estimates overlap with D's ACS coverage at a more specific cut; let D handle it. F focuses on districts as institutions, not demographics within them.

### Q2. School-district aggregate granularity — district-level only, or include school-level?

NCES publishes both district-level (LEA = Local Education Agency) and school-level (NCES School ID) aggregates. Two options:
- (a) **District-level only.** ~13K rows nationally per year.
- (b) **District-level + school-level.** ~100K rows nationally per year.

**Recommendation: (a) for F's first phase.** School-level is meaningful but ~10× more data; ship it as Phase 1b if demand surfaces.

### Q3. Special-district sub-typing model — match C's Q2 answer?

C's Q2 question (special_district sub-typing — one boundary type with a `kind` field, or one boundary type per kind) directly determines F's storage shape. If C answers (a) "one boundary type with kind field," F's `SpecialDistrictAttributes` matches. If C answers (b) "one boundary type per kind," F's `SpecialDistrictAttributes` becomes per-kind models too (or stays unified with a discriminator).

**Recommendation: defer until C Q2 is answered.** F's design will land with whatever C settles on. The sketch above assumes C answers (a).

### Q4. Funding-data granularity — totals only or break by source?

NCES CCD F-33 finance file publishes revenue by ~50 line items (federal Title I, state instruction, local property tax, etc.). Two options:
- (a) **Three rollups** (federal / state / local) plus a few specific line items (Title I, IDEA). Smaller schema.
- (b) **All ~50 line items.** Faithful to source; useful for analysts; wider schema.

**Recommendation: (a) for Phase 1; consider (b) as a Phase 1b expansion if analysts request specific line items not in the rollups.**

## Out of scope

- Voter registration / turnout (lives in the political domain — would be a separate sub-issue).
- Court records.
- 311 / municipal-services data (per-city; not nationally standardized).
- Police/fire incident data (privacy + per-city; not boundary-keyed in any standard way).

## Sequencing

- This PR (design v1) → maintainer Q1-Q4 → Phase 1 implementation (NCES CCD after C ships `school_district`) → Phase 2 (Special districts after C ships `special_district` + Q3 settled).

## References

- Parent: SW#189
- B PR #2: #206 (Vintage canonical)
- C design: #207 (`school_district` + `special_district` come from there)
- NCES CCD: nces.ed.gov/ccd/
- NCES EDGE: nces.ed.gov/programs/edge/
- Census Special Districts: census.gov/programs-surveys/cog/about/special-districts.html
