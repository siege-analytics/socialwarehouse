# Event

**App**: `socialwarehouse.events`
**Table**: `sw_event`
**Mixin**: `SourceAwareModel`

Unified event supertype. The shared query surface that ties the entire ontology together. "All events involving Agent X" is answered by querying EventParticipant joined to Event.

## Event types

| Type | Subtype model | Table |
|---|---|---|
| `transaction` | (none — linked via transactions) | — |
| `corporate` | `CorporateEvent` | `sw_event_corporate` |
| `spatiotemporal` | `SpatioTemporalEvent` | `sw_event_spatiotemporal` |
| `electoral` | `ElectoralEvent` | `sw_event_electoral` |

## Shared query surface

```python
EventParticipant.objects.filter(agent_uuid=some_uuid)
    .select_related("event")
    .order_by("-event__event_date")
```

Returns all events involving an agent across all event types.

## EventParticipant roles

source, target, subject, witness, candidate, winner, predecessor, successor, affected, other.

## Auto-derived fields

- `year` — derived from `event_date` on save
