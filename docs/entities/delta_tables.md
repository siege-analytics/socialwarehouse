# delta/tables.py (Python module, socialwarehouse.delta.tables)

**Definition:** `socialwarehouse/delta/tables.py`
**Surveyed at:** 2026-05-19 (seeded via survey-context NO-DOC path during D7 SCD-decision write-up)
**Owner:** delta / warehouse-scale maintainers

## Shape

Centralized registry of Spark `StructType` schemas + a `TABLES` dict mapping registry keys (`bronze.*`, `silver.*`, `gold.*`) to `{schema, path, partition_by, description}` records. Resolved paths come from `delta/config.py:get_table_path`.

## Tiers

| Tier | Purpose | Tables defined |
|---|---|---|
| Bronze | Raw ingested data, untransformed | `bronze.addresses`, `bronze.boundaries` |
| Silver | Cleaned / typed / partitioned | `silver.addresses`, `silver.demographics`, `silver.boundaries` (path-only) |
| Gold | Analytics-ready, joined | `gold.enriched_addresses` |

## SCD2 vs point-in-time keying

**`SILVER_DEMOGRAPHICS` is intentionally NOT SCD2.** Census demographic estimates are point-in-time snapshots with a natural composite key: `(geoid, vintage_year, summary_level, variable_code, survey_type)`. Revisions are published as a NEW `vintage_year` or `survey_type`, never as in-place edits to the same composite key — the version IS the natural key. Adding `is_current` / `effective_from` / `effective_to` would duplicate version-tracking the composite key already provides.

By contrast, the warehouse-side `DimGeography` IS SCD2: geographies do get revised within a vintage (TIGER/Line corrections, redistricting amendments, boundary mergers) and the same `(geoid, vintage_year)` key can have multiple effective spans. SCD2 fields are load-bearing there. (D7 / SW#129 — intentional asymmetry, documented.)

## Callers / consumers

- `socialwarehouse/delta/enrichment.py` — resolves `addresses_table` arg against `TABLES`.
- `socialwarehouse/delta/io.py` (if present) — uses schemas for `spark.read.schema(...)`.
- Future Spark jobs should resolve via this registry rather than re-typing paths.

## Cross-references

- `delta/config.py:get_table_path` — provides the tier path prefix.
- `delta/enrichment.py` — primary `TABLES` consumer.
- Warehouse `DimGeography` (siege_utilities.geo / SW warehouse) — the SCD2 counterpart documented above.

## Known assumptions / gotchas

- **Registry keys are flat strings** (e.g. `"silver.addresses"`). Typos route through `enrichment.py`'s `addresses_table` validation, which post-D8 raises `ValueError` rather than falling through to a raw-path read.
- **`SILVER_DEMOGRAPHICS` lacks SCD2 fields by design** — see SCD2 vs point-in-time keying above. Don't add `is_current` / `effective_from` / `effective_to` without first updating that section.

## Survey log

- 2026-05-19: Seeded via survey-context NO-DOC path during D7 / SW#129 fix. Documents the intentional SCD2 asymmetry: `DimGeography` is SCD2 because geographies revise within a vintage; `SILVER_DEMOGRAPHICS` is not because Census revisions ship as new vintages, not edits. Inline comment added above `SILVER_DEMOGRAPHICS` capturing the same rationale at the call site.
