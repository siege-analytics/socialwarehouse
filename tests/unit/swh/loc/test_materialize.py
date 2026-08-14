"""Tests for #73: LoC / congress-legislators -> civic-ontology Person.

Pure-Python tests cover the record mappers (Person kwargs, identifiers,
terms, attestation payload) in isolation. The Django-DB test covers the
idempotent upsert into the real ontology models (Agent + Person +
EntityIdentifier + Attestation + Office/OfficeTerm).
"""

from datetime import date

import pytest


def _bernie():
    """A Bernie-shaped record: multiple FEC ids (one Person, many candidacies),
    a House term then a Senate term."""
    return {
        "id": {
            "bioguide": "S000033",
            "govtrack": 400357,
            "opensecrets": "N00000528",
            "fec": ["H8VT01016", "S4VT00033"],
            "wikipedia": "Bernie Sanders",
        },
        "name": {"first": "Bernard", "last": "Sanders", "official_full": "Bernard Sanders"},
        "bio": {"birthday": "1941-09-08", "gender": "M"},
        "terms": [
            {"type": "rep", "start": "1991-01-03", "end": "1993-01-05",
             "state": "VT", "district": 0, "party": "Independent"},
            {"type": "sen", "start": "2007-01-04", "end": "2013-01-03",
             "state": "VT", "party": "Independent"},
        ],
    }


class TestPersonKwargs:
    def test_names_and_birth_year(self):
        from swh.loc import mappings

        out = mappings.person_kwargs(_bernie())
        assert out["full_name"] == "Bernard Sanders"
        assert out["given_name"] == "Bernard"
        assert out["family_name"] == "Sanders"
        assert out["birth_year"] == 1941
        assert out["data_source"] == "loc_bioguide"
        assert out["source_record_id"] == "S000033"
        assert out["jurisdiction_level"] == "federal"

    def test_full_name_falls_back_when_no_official_full(self):
        from swh.loc import mappings

        rec = {"id": {"bioguide": "X1"}, "name": {"first": "Ada", "middle": "B", "last": "Lovelace"}}
        assert mappings.person_kwargs(rec)["full_name"] == "Ada B Lovelace"

    def test_missing_bio_is_safe(self):
        from swh.loc import mappings

        rec = {"id": {"bioguide": "X1"}, "name": {"first": "A", "last": "B"}}
        assert mappings.person_kwargs(rec)["birth_year"] is None


class TestIdentifiers:
    def test_multiple_fec_ids_each_become_a_row(self):
        from swh.loc import mappings

        out = mappings.identifiers(_bernie())
        fec = [r for r in out if r["identifier_type"] == "fec_candidate_id"]
        assert {r["identifier_value"] for r in fec} == {"H8VT01016", "S4VT00033"}

    def test_bioguide_and_crosswalks_present(self):
        from swh.loc import mappings

        types = {r["identifier_type"] for r in mappings.identifiers(_bernie())}
        assert "bioguide_id" in types
        assert "govtrack_id" in types
        assert "opensecrets_id" in types

    def test_empty_ids_dropped(self):
        from swh.loc import mappings

        rec = {"id": {"bioguide": "X1", "govtrack": None, "fec": []}}
        types = {r["identifier_type"] for r in mappings.identifiers(rec)}
        assert types == {"bioguide_id"}


class TestTerms:
    def test_chamber_and_district_and_congress(self):
        from swh.loc import mappings

        terms = mappings.terms(_bernie())
        assert len(terms) == 2
        house, senate = terms
        assert house["office"]["chamber"] == "house"
        assert house["office"]["district_number"] == "0"
        assert house["office"]["name"] == "US House VT-0"
        assert house["start_date"] == date(1991, 1, 3)
        assert house["congress_number"] == 102  # 1991 -> 102nd Congress
        assert senate["office"]["chamber"] == "senate"
        assert senate["office"]["district_number"] == ""
        assert senate["office"]["name"] == "US Senate VT"

    def test_non_congressional_terms_skipped(self):
        from swh.loc import mappings

        rec = {"id": {"bioguide": "X1"}, "terms": [{"type": "prez", "start": "2001-01-20", "state": "US"}]}
        assert mappings.terms(rec) == []


class TestAttestationPayload:
    def test_content_hash_is_stable_and_sensitive(self):
        from swh.loc import mappings

        v1 = mappings.bio_attestation_values(_bernie())
        assert mappings.content_hash(v1) == mappings.content_hash(dict(v1))
        v2 = dict(v1)
        v2["terms_count"] = 999
        assert mappings.content_hash(v1) != mappings.content_hash(v2)

    def test_bioguide_id_none_when_absent(self):
        from swh.loc import mappings

        assert mappings.bioguide_id({"id": {}}) is None


@pytest.mark.django_db
class TestMaterializeOntology:
    """Upsert into the real ontology models; verify shape + idempotency."""

    def test_upsert_creates_ontology_graph_and_is_idempotent(self):
        from socialwarehouse.agents.models import Person
        from socialwarehouse.core.agent import Agent
        from socialwarehouse.core.attestation import Attestation
        from socialwarehouse.core.mixins import generate_entity_uuid5
        from socialwarehouse.core.models import EntityIdentifier
        from socialwarehouse.political.models import Office, OfficeTerm
        from swh.loc.materialize import materialize_legislators

        counts = materialize_legislators([_bernie()])
        assert counts == {"persons": 1, "office_terms": 2, "skipped": 0}

        person_uuid = generate_entity_uuid5("loc_bioguide", "S000033")
        person = Person.objects.get(entity_uuid=person_uuid)
        assert person.full_name == "Bernard Sanders"
        # Person is linked to its Agent hub (Agent subtype).
        assert person.agent is not None
        assert person.agent.subtype == "person"
        assert Agent.objects.filter(entity_uuid=person.agent.entity_uuid).exists()

        # Both FEC candidate ids resolve to the one Person (the #74 seed).
        fec_ids = set(
            EntityIdentifier.objects.filter(
                entity_uuid=person_uuid, identifier_type="fec_candidate_id"
            ).values_list("identifier_value", flat=True)
        )
        assert fec_ids == {"H8VT01016", "S4VT00033"}

        # Exactly one canonical bio attestation.
        canonical = Attestation.for_entity("person", person_uuid, is_canonical=True)
        assert canonical.count() == 1
        assert canonical.first().attestation_source_tier == "authoritative"

        # Two congressional terms across a House and a Senate Office.
        assert OfficeTerm.objects.filter(person_uuid=person_uuid).count() == 2
        assert Office.objects.filter(chamber="house", jurisdiction_state="VT").exists()
        assert Office.objects.filter(chamber="senate", jurisdiction_state="VT").exists()

        # Re-run: idempotent — no duplicate Person / attestation / terms.
        counts2 = materialize_legislators([_bernie()])
        assert counts2 == {"persons": 1, "office_terms": 2, "skipped": 0}
        assert Person.objects.filter(entity_uuid=person_uuid).count() == 1
        assert Attestation.for_entity("person", person_uuid, is_canonical=True).count() == 1
        assert OfficeTerm.objects.filter(person_uuid=person_uuid).count() == 2

    def test_record_without_bioguide_is_skipped(self):
        from swh.loc.materialize import materialize_legislators

        counts = materialize_legislators([{"id": {}, "name": {"first": "No", "last": "Anchor"}}])
        assert counts == {"persons": 0, "office_terms": 0, "skipped": 1}
