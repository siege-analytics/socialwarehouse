# <Entity name> (<type>, <namespace>)

**Definition:** `<file:line>`
**Surveyed at:** YYYY-MM-DD
**Owner:** <team / role>

## Shape

### Fields / signature / columns

<list — declared fields with type + constraints>

### Constraints

<unique_together, indexes, FK targets, NOT NULL, defaults>

### Lookups / methods of interest

<for Django models: lookups callers rely on; for functions: documented contract>

## Callers / consumers

<grep result trimmed to load-bearing references>

## Cross-references

<FKs in/out, related models, downstream tables / endpoints>

## Known assumptions / gotchas

<things authors get wrong; e.g. "object_id is CharField geoid-string, NOT integer PK">

## Survey log

- YYYY-MM-DD: <what changed / who verified / why update>
