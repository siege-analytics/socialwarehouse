"""Tests for the FEC-gold → SW dimensional loaders (SW#366).

``load_fec_agents`` and ``load_fec_attestations`` are set-based in-DB
``INSERT...SELECT`` commands that read the ``gold`` schema (an FDW mirror of
electinfo.gold in production). These tests stand up minimal ``gold.*`` fixture
tables in the test DB and exercise the real commands, pinning:

* identity — the in-DB ``uuid_generate_v5`` matches ``generate_entity_uuid5``
  (Agent = uuid5(subtype, ds, src); subtype = uuid5(ds, src)),
* the Agent↔subtype FK linkage across committee / person / organization,
* mapping of raw FEC ``committee_type`` codes -> the model choice vocabulary,
* birth_year hardening (dirty/non-4-digit -> NULL, no smallint overflow),
* re-run refresh (ON CONFLICT DO UPDATE) of descriptive fields,
* attestation shape A — base ``core.Attestation`` (kind='fec', canonical) with
  honest provenance only, and congress-sourced officeholders EXCLUDED,
* idempotency — re-running nets zero new rows / enriches canonical in place.

Requires the ``uuid-ossp`` extension; the postgis CI image ships it and creates
POSTGRES_USER as a superuser, so ``CREATE EXTENSION`` succeeds in setUp.
"""

from __future__ import annotations

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase

from socialwarehouse.core.mixins import generate_entity_uuid5


class _GoldFixture(TransactionTestCase):
    """Create minimal gold.* fixture tables + uuid-ossp for the loaders."""

    def setUp(self):
        with connection.cursor() as c:
            c.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
            c.execute("CREATE SCHEMA IF NOT EXISTS gold")
            for t in ("committee_entities", "candidate_entities",
                      "officeholder_entities", "vendor_entities",
                      "employer_entities", "individual_entities"):
                c.execute(f"DROP TABLE IF EXISTS gold.{t}")
            c.execute("""
                CREATE TABLE gold.committee_entities (
                    catalog text, id text, fec_committee_id text, committee_name text,
                    committee_type text, eff_start_dt date, eff_stop_dt date,
                    _synced_at timestamp)
            """)
            c.execute("""
                CREATE TABLE gold.candidate_entities (
                    catalog text, id text, fec_candidate_id text, candidate_name text,
                    first_name text, last_name text, name_suffix text, _synced_at timestamp)
            """)
            c.execute("""
                CREATE TABLE gold.officeholder_entities (
                    catalog text, id text, bioguide_id text, name text,
                    first_name text, last_name text, birth_year text, _synced_at timestamp)
            """)
            c.execute("""
                CREATE TABLE gold.vendor_entities (
                    catalog text, id text, name text, _synced_at timestamp)
            """)
            # employer + individual share vendor/person shape; needed so
            # `--entity all` (which iterates every FEC spec) has all tables.
            c.execute("""
                CREATE TABLE gold.employer_entities (
                    catalog text, id text, name text, _synced_at timestamp)
            """)
            c.execute("""
                CREATE TABLE gold.individual_entities (
                    catalog text, id text, name text, _synced_at timestamp)
            """)
            c.execute("""
                INSERT INTO gold.employer_entities (catalog, id, name, _synced_at)
                VALUES ('FEC', 'E-0001', 'GLOBEX CORP', '2026-03-11 15:59:59')
            """)
            c.execute("""
                INSERT INTO gold.individual_entities (catalog, id, name, _synced_at)
                VALUES ('FEC', 'IND-0001', 'SMITH, PAT', '2026-03-11 15:59:59')
            """)
            c.execute("""
                INSERT INTO gold.committee_entities
                    (catalog, fec_committee_id, committee_name, committee_type, _synced_at)
                VALUES
                    ('FEC', 'C00000001', 'TEST PAC', 'Q', '2026-03-11 15:59:59'),
                    ('FEC', 'C00000002', 'BLANK-TYPE PAC', '', '2026-03-11 15:59:59'),
                    ('FEC', 'C00000003', 'JANE FOR HOUSE', 'H', '2026-03-11 15:59:59'),
                    ('FEC', 'C00000004', 'STATE PARTY', 'X', '2026-03-11 15:59:59'),
                    ('FEC', '', 'NO ID PAC', 'N', '2026-03-11 15:59:59')
            """)
            c.execute("""
                INSERT INTO gold.candidate_entities
                    (catalog, fec_candidate_id, candidate_name, first_name, last_name, _synced_at)
                VALUES
                    ('FEC', 'H0TX00001', 'DOE, JANE', 'JANE', 'DOE', '2026-03-11 15:59:59')
            """)
            c.execute("""
                INSERT INTO gold.officeholder_entities
                    (catalog, bioguide_id, name, first_name, last_name, birth_year, _synced_at)
                VALUES
                    ('congress_gov', 'D000001', 'DOE, JOHN', 'JOHN', 'DOE', '1961', '2026-03-11 15:59:59'),
                    ('congress_gov', 'D000002', 'ROE, SUE', 'SUE', 'ROE', '1961-1962', '2026-03-11 15:59:59')
            """)
            c.execute("""
                INSERT INTO gold.vendor_entities (catalog, id, name, _synced_at)
                VALUES ('FEC', 'V-0001', 'ACME PRINTING', '2026-03-11 15:59:59')
            """)

    def tearDown(self):
        with connection.cursor() as c:
            for t in ("committee_entities", "candidate_entities",
                      "officeholder_entities", "vendor_entities",
                      "employer_entities", "individual_entities"):
                c.execute(f"DROP TABLE IF EXISTS gold.{t}")


class TestLoadFecAgents(_GoldFixture):

    def test_committee_agents_and_subtypes_with_uuid5(self):
        from socialwarehouse.agents.models import Committee
        from socialwarehouse.core.agent import Agent

        call_command("load_fec_agents", "--entity=committee", verbosity=0)

        # The blank fec_committee_id row is filtered out (4 of 5 load).
        self.assertEqual(Agent.objects.filter(subtype="committee").count(), 4)
        self.assertEqual(Committee.objects.count(), 4)

        c1 = Committee.objects.select_related("agent").get(source_system_id="C00000001")
        self.assertEqual(c1.name, "TEST PAC")
        self.assertEqual(c1.entity_uuid, generate_entity_uuid5("fec", "C00000001"))
        self.assertEqual(
            c1.agent.entity_uuid, generate_entity_uuid5("committee", "fec", "C00000001")
        )
        self.assertEqual(c1.agent.subtype, "committee")
        self.assertEqual(c1.agent.lifecycle_state, "active")

    def test_committee_type_maps_fec_codes_to_choice_vocabulary(self):
        from socialwarehouse.agents.models import Committee

        call_command("load_fec_agents", "--entity=committee", verbosity=0)
        self.assertEqual(Committee.objects.get(source_system_id="C00000001").committee_type, "pac")       # Q
        self.assertEqual(Committee.objects.get(source_system_id="C00000003").committee_type, "campaign")  # H
        self.assertEqual(Committee.objects.get(source_system_id="C00000004").committee_type, "party")     # X
        self.assertEqual(Committee.objects.get(source_system_id="C00000002").committee_type, "other")     # blank

        # Every loaded committee_type is within the model's declared vocabulary.
        valid = {v for v, _ in Committee._meta.get_field("committee_type").choices}
        self.assertTrue(set(Committee.objects.values_list("committee_type", flat=True)) <= valid)

    def test_candidate_loads_as_person(self):
        from socialwarehouse.agents.models import Person
        from socialwarehouse.core.agent import Agent

        call_command("load_fec_agents", "--entity=candidate", verbosity=0)
        self.assertEqual(Agent.objects.filter(subtype="person").count(), 1)
        p = Person.objects.select_related("agent").get(source_record_id="H0TX00001")
        self.assertEqual(p.full_name, "DOE, JANE")
        self.assertEqual(p.given_name, "JANE")
        self.assertEqual(p.family_name, "DOE")
        self.assertEqual(p.entity_uuid, generate_entity_uuid5("fec", "H0TX00001"))
        self.assertEqual(
            p.agent.entity_uuid, generate_entity_uuid5("person", "fec", "H0TX00001")
        )

    def test_vendor_loads_as_organization(self):
        from socialwarehouse.agents.models import Organization
        from socialwarehouse.core.agent import Agent

        call_command("load_fec_agents", "--entity=vendor", verbosity=0)
        self.assertEqual(Agent.objects.filter(subtype="organization").count(), 1)
        org = Organization.objects.select_related("agent").get(source_record_id="V-0001")
        self.assertEqual(org.name, "ACME PRINTING")
        self.assertEqual(org.industry_system, "naics")
        self.assertEqual(org.entity_uuid, generate_entity_uuid5("fec", "V-0001"))
        self.assertEqual(
            org.agent.entity_uuid, generate_entity_uuid5("organization", "fec", "V-0001")
        )

    def test_officeholder_birth_year_dirty_value_is_nulled(self):
        from socialwarehouse.agents.models import Person

        # 'D000002' has birth_year '1961-1962' — must NOT overflow smallint; -> NULL.
        call_command("load_fec_agents", "--entity=officeholder", verbosity=0)
        self.assertEqual(Person.objects.get(source_record_id="D000001").birth_year, 1961)
        self.assertIsNone(Person.objects.get(source_record_id="D000002").birth_year)
        # Officeholder entities are congress-sourced.
        self.assertEqual(
            Person.objects.get(source_record_id="D000001").agent.data_source, "congress"
        )

    def test_reload_refreshes_descriptive_fields(self):
        from socialwarehouse.agents.models import Committee

        call_command("load_fec_agents", "--entity=committee", verbosity=0)
        # Simulate corrected gold: rename + retype an existing committee.
        with connection.cursor() as c:
            c.execute("UPDATE gold.committee_entities SET committee_name='RENAMED PAC', "
                      "committee_type='O' WHERE fec_committee_id='C00000001'")
        call_command("load_fec_agents", "--entity=committee", verbosity=0)

        c1 = Committee.objects.get(source_system_id="C00000001")
        self.assertEqual(c1.name, "RENAMED PAC")
        self.assertEqual(c1.committee_type, "super_pac")  # 'O' -> super_pac
        self.assertEqual(Committee.objects.count(), 4)  # no duplication

    def test_idempotent(self):
        from socialwarehouse.core.agent import Agent

        call_command("load_fec_agents", "--entity=committee", verbosity=0)
        call_command("load_fec_agents", "--entity=committee", verbosity=0)
        self.assertEqual(Agent.objects.filter(subtype="committee").count(), 4)


class TestLoadFecAttestations(_GoldFixture):

    def test_canonical_attestation_with_honest_provenance(self):
        from socialwarehouse.core.attestation import Attestation

        call_command("load_fec_agents", "--entity=committee", verbosity=0)
        call_command("load_fec_attestations", "--entity=committee", verbosity=0)

        self.assertEqual(Attestation.objects.filter(entity_subtype="committee").count(), 4)
        att = Attestation.objects.get(
            entity_id=generate_entity_uuid5("fec", "C00000001"),
            entity_subtype="committee",
        )
        self.assertEqual(att.attestation_kind, "fec")
        self.assertTrue(att.is_canonical)
        # Honest provenance only — no fabricated form/tier metadata.
        self.assertEqual(att.attestation_source_tier, "unknown")
        self.assertEqual(att.attested_values["source_catalog"], "FEC")
        self.assertEqual(att.attested_values["source_system"], "fec_bulk")
        self.assertIn("synced_at", att.attested_values)
        # No form-level fields (base Attestation, not FECAttestation).
        self.assertNotIn("fec_form_type", att.attested_values)

    def test_officeholder_excluded_from_fec_attestations(self):
        from socialwarehouse.core.attestation import Attestation

        # Load the officeholder ENTITY, then run the FEC attestation loader for all.
        call_command("load_fec_agents", "--entity=officeholder", verbosity=0)
        call_command("load_fec_attestations", "--entity=all", verbosity=0)

        # The congress-sourced officeholder must NOT receive an FEC attestation
        # (would be a contradictory provenance record).
        officeholder_id = generate_entity_uuid5("congress", "D000001")
        self.assertEqual(Attestation.objects.filter(entity_id=officeholder_id).count(), 0)

    def test_one_canonical_per_entity_and_idempotent_enrich(self):
        from socialwarehouse.core.attestation import Attestation

        call_command("load_fec_agents", "--entity=committee", verbosity=0)
        call_command("load_fec_attestations", "--entity=committee", verbosity=0)
        call_command("load_fec_attestations", "--entity=committee", verbosity=0)

        # Re-run enriches in place (ON CONFLICT DO UPDATE) — no duplication.
        self.assertEqual(Attestation.objects.filter(entity_subtype="committee").count(), 4)
        canon = Attestation.objects.filter(
            entity_id=generate_entity_uuid5("fec", "C00000001"),
            entity_subtype="committee",
            attestation_kind="fec",
            is_canonical=True,
        )
        self.assertEqual(canon.count(), 1)
