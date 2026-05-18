# DemographicSnapshot (Django model, siege_utilities.geo.django.models.demographics)

**Definition:** `siege_utilities/geo/django/models/demographics.py` (upstream — not in this repo)
**Surveyed at:** 2026-05-18
**Owner:** SU maintainers (upstream); SW callers responsible for local survey log

## Shape (relevant fields for SW callers)

| Field | Type | Notes |
|---|---|---|
| `content_type` | ForeignKey(ContentType) | generic-FK type half |
| `object_id` | **CharField(max_length=20)** | **GEOID string** — NOT an integer PK |
| `content_object` | GenericForeignKey | resolves via (content_type, object_id) |
| `year` | PositiveSmallIntegerField | db_index'd; 1990-2050 |
| `dataset` | CharField(max_length=10) | db_index'd; choices from DATASET_CHOICES |
| `vintage` | PositiveSmallIntegerField | nullable; API vintage may differ from year |
| `values` | JSONField(default=dict) | variable_code → value |
| `moe_values` | JSONField(default=dict, blank=True) | variable_code → margin of error |
| `total_population` | PositiveIntegerField | nullable; db_index'd; computed summary (B01001_001E) |
| `median_household_income` | PositiveIntegerField | nullable |

(Other computed-summary fields exist; consult upstream for full list.)

### Lookups callers must use correctly

- **`filter(object_id=geoid_string)`** — geoid string-matched. NOT `filter(object_id=int_pk)`.
- `filter(content_type=ct, object_id=geoid)` — the canonical SW pattern.
- `filter(year=..., dataset=...)` — time + source scoping.

## Callers / consumers (SW)

- `socialwarehouse/api/geo/views.py:_get_demographics_for_boundaries` — queries by content_type + geoid. The original A2 review (SW#113) incorrectly claimed this query was broken because `object_id` was assumed integer; verifying the field type via this page shows the existing query is correct.

## Known assumptions / gotchas

- **`object_id` is CharField geoid-string, NOT IntegerField PK.** This is the canonical example of why this skill exists: a reviewer (and would-be author) without consulting upstream model can incorrectly assume Django's generic-FK convention (object_id = int PK pointing at content_type.id). For SU's boundary models, the design is geoid-keyed for stability across vintages — boundary PK can change but geoid does not.
- **`values` / `moe_values` are JSONFields** — variable codes appear as JSON keys, NOT as columns. Don't try `filter(values__B01001_001E=...)` portably across DB engines; use JSONField KeyTransform with care.
- **Cross-app dependency.** Upstream changes affect SW callers. Local survey log records SU-version where the shape was last verified.

## Survey log

- 2026-05-18: Seeded after the A2 / SW#113 retraction. SU upstream (commit unrecorded; verify at next survey) confirms `object_id = CharField(max_length=20)`. This is the worked example in the global skill demonstrating the value of the consult-docs step.
