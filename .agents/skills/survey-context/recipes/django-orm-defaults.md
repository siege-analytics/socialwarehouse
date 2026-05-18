# Recipe: Django ORM `defaults={...}` kwarg validation

**Surveyor command:**

```bash
python -c "from <module> import <Model>; print(sorted(f.name for f in <Model>._meta.get_fields()))"
```

Compare the output against every `defaults={...}` dict in callers.

**What to record in the entity page:**
- Full `_meta.get_fields()` output (or at least the writable fields callers can pass to `update_or_create`).
- Any fields that have non-trivial defaults (`auto_now`, `auto_now_add`, `default=callable`) — these are usually NOT to be passed in `defaults`.
- Any fields callers commonly get wrong (rename history, similar names, fields-on-related-model that look like they're on this one).

**Drift signals:**
- A loader writes `defaults={"X": ...}` where `X` is not in the entity-page field list.
- A field was renamed in the model but the entity page still lists the old name.
- A loader's `defaults` dict is missing a required-non-null field (no default at DB level, no default in model).

**Common-mistake patterns this recipe catches:**
- W1 / SW#105: loader wrote 6 keys (`day_suffix`, `day_name`, `weekday`, etc.) that aren't on `DimTime`. Consulting the entity page would have shown the actual field list.
- W2 / SW#106: loader wrote `census_year` when the model had `decennial_census_year`. Renaming the model field was the right fix; the entity page now records the post-fix name so future callers don't reintroduce the old name.

**Composition with scanner #117:**

The static scanner at `claude-configs-public#117` enforces this recipe automatically for same-file models. For **cross-file** model imports (which is the common case in this repo), the scanner punts and this recipe is the author-time check. The survey-context skill consults the entity page rather than re-running introspection.
