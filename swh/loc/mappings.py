"""congress-legislators / LoC record -> civic-ontology canonical shapes.

Pure-Python mappers (no Django, no Spark) so they unit-test in isolation,
mirroring the `swh/voters` row-mapper convention. Each function turns one
`unitedstates/congress-legislators` record into an ontology piece the
materializer upserts. Person identity is anchored on the stable
`bioguide_id` so the same human resolves to the same Person across the
current + historical files and across re-ingests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

# data_source that anchors the Person UUID5. bioguide_id is the identity
# key, so the Person UUID is uuid5(LOC_DATA_SOURCE, bioguide_id).
LOC_DATA_SOURCE = "loc_bioguide"

# congress-legislators term "type" -> ontology Office.chamber.
_CHAMBER = {"rep": "house", "sen": "senate"}

# congress-legislators id{} keys -> EntityIdentifier.identifier_type.
_ID_SYSTEMS = {
    "bioguide": "bioguide_id",
    "govtrack": "govtrack_id",
    "opensecrets": "opensecrets_id",
    "icpsr": "icpsr_id",
    "wikipedia": "wikipedia",
    "wikidata": "wikidata_id",
    "ballotpedia": "ballotpedia",
    "votesmart": "votesmart_id",
    "cspan": "cspan_id",
}


def bioguide_id(rec: dict) -> str | None:
    """The stable identity anchor, or None when absent (record is skippable)."""
    return (rec.get("id") or {}).get("bioguide")


def _year(datestr) -> int | None:
    if not datestr:
        return None
    try:
        return int(str(datestr)[:4])
    except (ValueError, TypeError):
        return None


def _parse_date(datestr) -> date | None:
    if not datestr:
        return None
    try:
        y, m, d = str(datestr)[:10].split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def person_kwargs(rec: dict) -> dict:
    """Person model kwargs (minus entity_uuid, which the materializer sets)."""
    name = rec.get("name") or {}
    bio = rec.get("bio") or {}
    first = name.get("first") or ""
    last = name.get("last") or ""
    full = name.get("official_full") or " ".join(
        p for p in (first, name.get("middle"), last) if p
    ).strip()
    return {
        "full_name": full or last or first or "(unknown)",
        "given_name": first,
        "family_name": last,
        "middle_name": name.get("middle") or "",
        "name_suffix": name.get("suffix") or "",
        "birth_year": _year(bio.get("birthday")),
        "data_source": LOC_DATA_SOURCE,
        "jurisdiction_level": "federal",
        "jurisdiction_state": "",
        "source_record_id": bioguide_id(rec) or "",
    }


def identifiers(rec: dict) -> list[dict]:
    """External identifiers -> EntityIdentifier.register kwargs (no entity_uuid).

    The FEC candidate ids (a list) are the free, high-precision seed for
    the Person <-> Candidate crosswalk (#74): one human, one Person, many
    fec_candidate_id rows.
    """
    idblock = rec.get("id") or {}
    out: list[dict] = []
    for key, itype in _ID_SYSTEMS.items():
        val = idblock.get(key)
        if val in (None, ""):
            continue
        out.append(
            {"identifier_type": itype, "identifier_value": str(val), "data_source": LOC_DATA_SOURCE}
        )
    for fec in idblock.get("fec") or []:
        if fec:
            out.append(
                {"identifier_type": "fec_candidate_id", "identifier_value": str(fec), "data_source": LOC_DATA_SOURCE}
            )
    return out


def _congress_number(start: date | None) -> int | None:
    """1st Congress convened 1789; a new Congress every two years."""
    if not start:
        return None
    n = ((start.year - 1789) // 2) + 1
    return n if n > 0 else None


def terms(rec: dict) -> list[dict]:
    """Congressional service terms -> {office, start/end, term_type, congress}.

    Non-congressional term rows (no rep/sen type) are skipped.
    """
    out: list[dict] = []
    for t in rec.get("terms") or []:
        chamber = _CHAMBER.get(t.get("type"))
        if not chamber:
            continue
        state = (t.get("state") or "").upper()
        district = t.get("district")
        district_number = "" if district is None else str(district)
        start = _parse_date(t.get("start"))
        if start is None:
            continue
        house = chamber == "house"
        office_name = f"US {'House' if house else 'Senate'} {state}"
        if house and district_number != "":
            office_name = f"{office_name}-{district_number}"
        out.append(
            {
                "office": {
                    "name": office_name,
                    "jurisdiction_level": "federal",
                    "jurisdiction_state": state,
                    "chamber": chamber,
                    "district_number": district_number,
                },
                "start_date": start,
                "end_date": _parse_date(t.get("end")),
                "term_type": "elected",
                "congress_number": _congress_number(start),
                "party": t.get("party") or "",
            }
        )
    return out


def bio_attestation_values(rec: dict) -> dict:
    """The attested payload for the congress-legislators source.

    This is the structured public record. Additional bios (narrative LoC
    Biographical Directory text, a pre-Congress business-site bio) attach
    later as their own attestations with their own source_reference — the
    multi-source, each-cited requirement.
    """
    return {
        "source": LOC_DATA_SOURCE,
        "name": rec.get("name") or {},
        "bio": rec.get("bio") or {},
        "id": rec.get("id") or {},
        "terms_count": len(rec.get("terms") or []),
    }


def content_hash(values: dict) -> str:
    """Stable content hash of an attested_values payload for change detection."""
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
