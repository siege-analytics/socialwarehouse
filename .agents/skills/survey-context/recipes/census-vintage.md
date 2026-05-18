# Recipe: Census vintage / geoid handling

**Surveyor command:** Read the model definition + the loader + check vintage_year handling across both.

**What to record in the entity page:**
- `vintage_year` field type, validators, range
- `geoid` length expectations per `summary_level` (state=2, county=5, tract=11, block_group=12, block=15, cd=4, vtd=11, sldl/sldu varies)
- Whether the model uses SCD2 (`is_current`, `effective_from/to`) for vintage drift
- Whether `geoid` is the natural key or merely indexed

**Drift signals:**
- New `summary_level` value appears in a loader without being documented in the model's help_text or in this skill's per-entity page.
- `vintage_year` validator range extended (e.g. 2100 → 2200) without commit message naming why.
- A new fact table joins on `(geography, time)` but doesn't follow the SCD2 lookup convention (`filter(is_current=True)` or `filter(effective_from__lte=date) & filter(effective_to__gte=date|isnull=True)`).

**Common-mistake patterns this recipe catches:**
- Author assumes `geoid` is fixed-length 11 (tract) and writes a CharField(max_length=11) caller that breaks on block GEOIDs.
- Author queries `DimGeography.objects.filter(geoid=X)` and gets multiple rows because SCD2 keeps history; missed the `is_current=True` filter.
- Loader inserts a new vintage without setting `is_current=False` on the prior vintage, so two rows now claim is_current.
