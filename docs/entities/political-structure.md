# Political Structure

**App**: `socialwarehouse.political`

## Office → Seat → Election → Contest → Term

Five models form the political structure graph:

### Office (`sw_office`)

Persistent identity for a political office. "US House TX-07" persists across redistricting. Inherits `SourceAwareModel` + `IdentifiableModel`.

Merge key: `(jurisdiction_level, jurisdiction_state, chamber, district_number)`.

### Seat (`sw_seat`)

Plan-specific geographic realization of an Office. When redistricting changes boundaries, a new Seat is created for the same Office. The Office persists; the Seat is temporal.

### Election (`sw_election`)

An election event with date, jurisdiction, and type (general, primary, special, runoff). Inherits `SourceAwareModel`. Auto-derives `year` from `election_date`.

### ElectoralContest (`sw_electoral_contest`)

What is being contested in a specific election. Links an Office/Seat to an Election. Candidates are Persons with Role "candidate" pointing at this contest's office.

### OfficeTerm (`sw_office_term`)

Who holds an office and when. Handles regular terms, special election remainder terms, and appointments. `congress_number` field supports federal chamber numbering.

## Term types

elected, appointed, special_election, acting.
