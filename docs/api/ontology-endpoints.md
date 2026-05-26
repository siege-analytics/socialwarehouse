# Ontology API Endpoints

All endpoints require authentication (DRF Session or Basic). Read-only (GET only). Paginated (100 per page, max 1000).

## Agents (`/api/agents/`)

| Endpoint | ViewSet | Query params |
|---|---|---|
| `/api/agents/persons/` | PersonViewSet | `?search=`, `?jurisdiction_state=`, `?data_source=` |
| `/api/agents/committees/` | CommitteeViewSet | `?search=` |
| `/api/agents/organizations/` | OrganizationViewSet | `?search=` |
| `/api/agents/classifications/` | ClassificationViewSet | `?agent_uuid=`, `?as_of=YYYY-MM-DD` |
| `/api/agents/roles/` | RoleViewSet | `?agent_uuid=`, `?as_of=YYYY-MM-DD` |

### Temporal queries

Classification and Role viewsets support `as_of` filtering: returns records where `effective_from <= as_of` and (`effective_to >= as_of` or `effective_to IS NULL`).

## Political (`/api/political/`)

| Endpoint | ViewSet |
|---|---|
| `/api/political/offices/` | OfficeViewSet |
| `/api/political/seats/` | SeatViewSet |
| `/api/political/elections/` | ElectionViewSet |
| `/api/political/contests/` | ElectoralContestViewSet |
| `/api/political/terms/` | OfficeTermViewSet |

## Transactions (`/api/transactions/`)

| Endpoint | ViewSet | Query params |
|---|---|---|
| `/api/transactions/contributions/` | ContributionViewSet | `?from_agent_uuid=`, `?to_agent_uuid=`, `?jurisdiction_state=` |
| `/api/transactions/expenditures/` | ExpenditureViewSet | `?from_agent_uuid=`, `?to_agent_uuid=`, `?jurisdiction_state=` |
| `/api/transactions/transfers/` | TransferViewSet | `?from_agent_uuid=`, `?to_agent_uuid=`, `?jurisdiction_state=` |
| `/api/transactions/obligations/` | ObligationViewSet | `?agent_uuid=`, `?status=` |

## Events (`/api/events/`)

| Endpoint | ViewSet | Query params |
|---|---|---|
| `/api/events/` | EventViewSet | `?agent_uuid=`, `?event_type=` |

### Event detail response

The detail endpoint includes nested `participants`, `corporate_detail`, `spatiotemporal_detail`, and `electoral_detail` (each null if not applicable). The list endpoint includes a `participant_count` annotation instead of nested data.
