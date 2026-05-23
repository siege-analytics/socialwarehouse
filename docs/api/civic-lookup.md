# `/api/geo/civic_lookup/` — address → district memberships

The civic-lookup endpoint composes the F11 boundary-cache fields on `geo.Address` into a single response, optionally surfacing the canonical Point geometry (DRF-GIS GeoJSON) and the `DimPerson` records at that address.

Per the warehouse-first principle ([`docs/architecture.md`](../architecture.md)): the data shape is determined by the warehouse (cached on `Address` via F11 when the row was geocoded); this endpoint is a thin read-only projection.

## Endpoint

```
GET /api/geo/civic_lookup/?address=<str>[&state=<usps>][&include_people=true|false][&include_geometry=true|false]
```

Implementation: `socialwarehouse.api.geo.views.CivicLookupView` (DRF `APIView`); serializers under `socialwarehouse.api.geo.serializers.civic_lookup` use `rest_framework_gis.fields.GeometryField` for the optional GeoJSON Point.

### Query parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `address` | str | required | Free-form address string. v1 expects a USPS-shape comma-separated form (`"123 Main St, Austin, TX 78701"`); matched literally against existing `geo.Address` rows. |
| `state` | str (2-char USPS) | none | Restricts candidate Address rows to a single state. Useful when the input address string would match in multiple states. |
| `include_people` | bool | `false` | When `true`, includes a `people` block with the `DimPerson` rows at this Address. Off by default for PII-friendly responses. |
| `include_geometry` | bool | `false` | When `true`, includes the Address's geocoded `Point` (GeoJSON via DRF-GIS) on the `address.geom` field. |

`include_*` flags accept `true / false / 1 / 0 / yes / no` (case-insensitive).

## Response shapes

### `200 OK`

Districts are emitted only for non-null boundary-cache fields on the matched Address — null cache fields are OMITTED from the `districts` dict (not emitted as `null`). The names are best-effort lookups against `DimGeography` by `(geoid, vintage_year=address.census_year)`; `name: null` when no matching DimGeography row exists.

```json
{
  "address": {
    "id": 42,
    "primary_number": "123",
    "street_name": "Main",
    "street_suffix": "St",
    "city_name": "Austin",
    "state_abbreviation": "TX",
    "zip5": "78701",
    "zip4": "1234",
    "latitude": "30.2672000000000000",
    "longitude": "-97.7431000000000000",
    "geocoded": true,
    "geocode_source": "census-batch",
    "census_year": 2020,
    "geom": { "type": "Point", "coordinates": [-97.7431, 30.2672] }
  },
  "districts": {
    "state": { "geoid": "48", "name": "Texas" },
    "county": { "geoid": "48453", "name": "Travis County" },
    "tract": { "geoid": "48453000601", "name": null },
    "congressional": { "geoid": "4810", "name": "TX-10" }
  },
  "redistricting_cycle": {
    "cycle_year": 2020,
    "first_election_year": 2022
  },
  "people": {
    "count": 1,
    "items": [
      { "vendor": "ts", "vendor_voter_id": "TS001", "registration_state": "TX" }
    ]
  }
}
```

### `400 Bad Request`

Returned when the `address` query parameter is missing or empty.

```json
{
  "error": "address query parameter is required",
  "code": "missing_address"
}
```

### `404 Not Found`

Returned when no Address row matches the input. The hint surfaces the next-step endpoint operators can call to geocode a fresh address.

```json
{
  "error": "no matching Address row found",
  "code": "address_not_found",
  "hint": "POST or GET /api/geo/geocode/?address=<...> to resolve a new address before calling civic_lookup"
}
```

When `state=<usps>` was supplied, the 404 mentions the filter:

```json
{
  "error": "no matching Address row found in state TX",
  "code": "address_not_found",
  "hint": "POST or GET /api/geo/geocode/?address=<...> to resolve a new address before calling civic_lookup, or omit ?state= to broaden the search"
}
```

### `409 Conflict`

Returned when multiple Address rows match the input. The endpoint refuses to guess; the operator supplies more detail.

```json
{
  "error": "multiple Address rows match; refine the query",
  "code": "ambiguous_address",
  "candidate_count": 3,
  "hint": "supply ?state=<USPS> or include a more specific address line"
}
```

## v1 behavior notes

- **No live geocoding.** v1 looks up existing `geo.Address` rows only. To geocode a fresh address, call `/api/geo/geocode/` first, then call civic_lookup with the resolved address. A composed "geocode-then-civic-lookup" endpoint is a follow-on if operators ask.
- **F11 cache is authoritative.** If `cd_geoid` is null on the matched Address row, the response omits `congressional` entirely. We do NOT synthesize from a spatial query against `DimGeography.geometry`. This is a deliberate vintage-integrity choice: the cache row is the answer to "what district was this address in under the census_year plan?"; spatial fallback would answer "what district intersects this point under whatever plan is current?" — a subtly different question.
- **PII-friendly defaults.** `include_people=false` by default. The minimal `PersonSummarySerializer` returned when opted-in surfaces only `vendor`, `vendor_voter_id`, and `registration_state` — no name, DOB, contact info, scoring, or vote history.
- **No geometry by default.** `include_geometry=false` keeps the response light; opt in when the consumer specifically needs the Point.

## See also

- `docs/architecture.md` — the warehouse-first principle this endpoint expresses.
- `docs/entities/dim-person.md` — DimPerson natural key + the F11 boundary cache fields on `Address`.
- `socialwarehouse.api.geo.views` — sibling endpoints (`geocode`, `boundary_detail`, `proximity`, `intersections`) the civic_lookup endpoint composes.
- Refs: SW#272 (this), SW#250 (parent initiative), SW#251 (DimPerson substrate).
