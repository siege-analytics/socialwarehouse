# Committee

**App**: `socialwarehouse.agents`
**Table**: `sw_committee`
**Mixins**: `SourceAwareModel`, `IdentifiableModel`

A regulatory fundraising vehicle with lifecycle tracking. Covers PACs, party committees, campaign committees, and similar entities that register with regulatory bodies to raise and spend money. General civic concept — not FEC-specific. FEC-specific subtypes live in the enterprise layer.

## Fields

| Field | Type | Notes |
|---|---|---|
| `entity_uuid` | UUID | Deterministic UUID5 from identity components. Immutable. |
| `name` | CharField(255) | Current legal name |
| `committee_type` | CharField(20) | pac, super_pac, party, campaign, leadership, hybrid, other |
| `source_system_id` | CharField(100) | Registration ID from source regulatory body |
| `formation_date` | DateField | Nullable |
| `termination_date` | DateField | NULL = active |
| `name_history` | JSONField | List of `{name, effective_from, effective_to}` |

## Natural key

`(data_source, source_system_id)` — unique together.

## Related models

- **Classification** — effective-dated type tags (via `agent_uuid`)
- **Role** — effective-dated role assignments (via `agent_uuid` or `counterparty_uuid`)
- **RelationshipSponsor** — connected organization sponsorship
- **Contribution** — as `to_agent_uuid`
- **Expenditure** — as `from_agent_uuid`
- **Transfer** — as either side
