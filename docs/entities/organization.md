# Organization

**App**: `socialwarehouse.agents`
**Table**: `sw_organization`
**Mixins**: `SourceAwareModel`, `IdentifiableModel`

Employer, vendor, consultant, union, corporation, or other non-committee organizational entity. Matched by name + jurisdiction + industry across sources. Unlike Committee, Organization does not have regulatory registration IDs as a universal natural key — matching is softer.

## Fields

| Field | Type | Notes |
|---|---|---|
| `entity_uuid` | UUID | UUID5 from (name, jurisdiction_state, industry_code) |
| `name` | CharField(255) | Legal or commonly-known name |
| `industry_code` | CharField(20) | NAICS or SIC code |
| `industry_system` | CharField(10) | naics, sic, other |

## Related models

- **Classification** — effective-dated type tags (via `agent_uuid`)
- **RelationshipSponsor** — as sponsor of a committee
- **RelationshipSubsidiary** — parent/child corporate relationships
- **RelationshipCorporateSuccession** — merger, spinoff, split, rename
- **Expenditure** — as `to_agent_uuid` (vendor payments)
