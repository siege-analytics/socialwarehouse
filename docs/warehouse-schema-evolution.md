# Warehouse schema evolution

How to evolve the warehouse schema safely, end-to-end across both warehouse tiers (Delta Lake + PostGIS star schema). Mirrors the `Warehouse first, web app last` design order from [`docs/architecture.md`](architecture.md).

## When to evolve

Two common evolution shapes:

1. **Promoting a vendor-extras map key to a canonical column** — a key that started life in a `vendor_extras` map (Delta) / `*_extras` JSONField (PostGIS) is now stable enough to deserve type safety.
2. **Adding a new canonical column directly** — a new field appears in vendor data that we want to canonicalize from day one.

This document covers (1). Pattern (2) is a subset (skip the backfill step).

## Promotion playbook

### 1. Establish the case

Cite evidence in the design note for the promoting PR:

- The key appears in N≥3 importers (or is queried often enough to justify type safety despite single-vendor source).
- The key's value semantics are stable across importers (not "TS calls it foo and L2 calls it bar but they mean different things").
- A consumer is asking for typed queries that the Map<String,String> shape doesn't support cleanly.

If the evidence chain is empty, leave the key in the map.

### 2. Update the silver Delta schema

Edit the relevant `StructType` in `socialwarehouse/delta/tables.py`:

```python
SILVER_PERSONS = StructType([
    # ... existing fields ...
    StructField("new_canonical_field", StringType(), True),  # or appropriate type
    # vendor_extras remains; key removal happens at importer level.
])
```

Apply to the live table:

```sql
ALTER TABLE delta.`silver.persons` ADD COLUMNS (new_canonical_field STRING)
```

(Delta SQL via `spark.sql(...)`.)

### 3. Backfill from existing rows

```sql
UPDATE delta.`silver.persons`
SET new_canonical_field = vendor_extras['old_key_name']
WHERE vendor_extras['old_key_name'] IS NOT NULL
  AND new_canonical_field IS NULL
```

The `AND new_canonical_field IS NULL` clause makes the backfill idempotent — re-running it does not stomp on fresh writes.

### 4. Update each importer

Each vendor's silver-build job now writes the new column going forward. Two policy choices for the map key:

- **Retain the map key.** Storage cost is small; provenance is preserved; downstream code that read from `vendor_extras['old_key_name']` keeps working. Default choice.
- **Remove the map key on next ingest.** Cleaner; requires a deprecation period and importer migration.

Default to retain. Pivot to remove only if the map storage cost is real.

### 5. Add the Django field

Edit `socialwarehouse/warehouse/models/dimensions.py` (or `facts.py`):

```python
class DimPerson(models.Model):
    # ... existing fields ...
    new_canonical_field = models.CharField(max_length=128, blank=True, default="")
```

Generate and run the migration:

```bash
python manage.py makemigrations warehouse --name add_new_canonical_field
python manage.py migrate warehouse
```

Forward-only. Never edit an existing migration once it has landed on `main`.

### 6. Update the materialization job

The Spark→PostGIS materialization that reads from `silver.persons` and upserts into `sw_warehouse_dimperson` now populates the new PostGIS column from the new silver column.

If the materialization job uses an explicit column list, add the new column there. If it uses `df.write.jdbc(...)` over the full DataFrame, the addition is automatic.

### 7. Record the promotion

Append an entry to the table below in this document.

## Promotion log

| Date | Field promoted | From map key | Evidence-of-need | PR | Backfill date |
|---|---|---|---|---|---|
| _(no promotions yet)_ | | | | | |

## What does NOT need this playbook

- **Adding a new `score_type` value to `FactPersonScore`.** `score_type` is a free string field; new values are new rows, no schema change.
- **Adding a new entry to a `*_extras` JSONField.** That's exactly what the map is for. No coordination needed.
- **A vendor renaming a field on its side.** Importer change only; canonical column name does not move.

## What this playbook does NOT permit

- **Removing a canonical column** without a deprecation period. Removing breaks downstream queries; the right response is "deprecate, document, give consumers N releases to migrate, then remove."
- **Renaming a canonical column** in-place. Add the new name; deprecate the old; remove after a release.
- **Type changes on a canonical column.** Type narrowing breaks consumers; type widening confuses analytics. Add a new column at the new type; deprecate the old.
- **Editing the Django migration after it has landed.** Forward-only is the project rule.

## Why this lives in repo docs and not just in tribal knowledge

The `Map<String,String>` extension bag works only if there is a credible way to escape it. Without a documented promotion path, every "should this be in the bag?" question reopens the design debate. With this playbook, the answer is "yes for now, promote when the case is made per the steps above."

## Cross-references

- [`docs/architecture.md`](architecture.md) — warehouse-first, web-app-last design order.
- [`docs/entities/dim-person.md`](entities/dim-person.md) — the canonical Person model.
- [`docs/entities/fact-person-score.md`](entities/fact-person-score.md) — score vocabulary registry.
- [`docs/entities/fact-vote-history.md`](entities/fact-vote-history.md) — vote-event semantics.
