"""Load entity-level FEC provenance as base ``core.Attestation`` rows (shape A).

Per the grain ruling: gold entities are RESOLVED AGGREGATES, not single FEC
filings, so their provenance is attested with the BASE ``core.Attestation``
(kind='fec') — NOT ``FECAttestation``, whose form-level fields
(fec_form_type / parser_version / source_artifact_hash) are per-filing and
would be fabricated metadata for an aggregate. (The per-gift TRANSACTION
loader, which IS per-filing, uses FECAttestation with the real form fields.)

Honesty note: current gold entity tables carry NO provenance tail
(no attestation_tier / coverage_* / snapshot_*) — only ``catalog`` and
``_synced_at``. So attestations record only what gold actually states:

    attested_values      = {source_catalog, source_system, synced_at}
    attestation_source_tier = 'unknown'   (gold states no tier)
    attested_at          = _synced_at
    is_canonical         = True

When corrected stage-1b gold lands WITH the provenance tail, re-running this
command ENRICHES each canonical attestation in place (ON CONFLICT DO UPDATE):
real tier from attestation_tier, coverage_pct/state + snapshot into
attested_values. One canonical attestation per (entity, kind), updated — no
duplication, no partial-unique violation.

Idempotent: the attestation's own entity_uuid is a deterministic UUID5 of
(canonical, subtype, data_source, source_id), 1:1 with its entity, so
ON CONFLICT (entity_uuid) DO UPDATE both dedups and enriches.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from socialwarehouse.core.mixins import SW_NAMESPACE

# (subtype, data_source, gold table, source-id expr, filter). Source identity
# must match the entity load so entity_id lines up with the subtype's uuid.
#
# This command emits FEC-kind attestations only, so it covers ONLY FEC-catalog
# entities. Officeholder entities are congress/bioguide-sourced (ds='congress',
# gold catalog 'congress_gov'), so attesting them as kind='fec'/source_system
# 'fec_bulk' would be a contradictory, dishonest provenance record — they are
# deliberately excluded here and get their provenance from a future
# congress-provenance loader. (The officeholder ENTITY still loads via
# load_fec_agents; only its FEC attestation is omitted.)
ATT_SPECS = {
    "committee":  ("committee",    "fec", "committee_entities",  "g.fec_committee_id", "g.fec_committee_id is not null and g.fec_committee_id <> ''"),
    "candidate":  ("person",       "fec", "candidate_entities",  "g.fec_candidate_id", "g.fec_candidate_id is not null and g.fec_candidate_id <> ''"),
    "individual": ("person",       "fec", "individual_entities", "g.id",               "g.id is not null and g.id <> ''"),
    "vendor":     ("organization", "fec", "vendor_entities",     "g.id",               "g.id is not null and g.id <> ''"),
    "employer":   ("organization", "fec", "employer_entities",   "g.id",               "g.id is not null and g.id <> ''"),
}
ORDER = ["committee", "candidate", "vendor", "employer", "individual"]


class Command(BaseCommand):
    help = "Load entity-level FEC provenance as base core.Attestation rows (kind='fec', canonical)."

    def add_arguments(self, parser):
        parser.add_argument("--entity", default="all", choices=["all", *ATT_SPECS])

    def handle(self, *args, **opts):
        ns = str(SW_NAMESPACE)
        which = ORDER if opts["entity"] == "all" else [opts["entity"]]
        with connection.cursor() as cur:
            for key in which:
                subtype, ds, table, src, where = ATT_SPECS[key]

                # entity_id = the attested subtype's own uuid = uuid5(ds, src).
                entity_id = f"uuid_generate_v5('{ns}'::uuid, '{ds}|' || lower(trim({src})))"
                # The attestation's OWN id — deterministic, 1:1 with its entity+kind.
                own_uuid = (
                    f"uuid_generate_v5('{ns}'::uuid, "
                    f"'attestation|fec|canonical|{subtype}|{ds}|' || lower(trim({src})))"
                )
                # Honest provenance from what current gold actually states.
                attested_values = (
                    "jsonb_strip_nulls(jsonb_build_object("
                    "'source_catalog', nullif(trim(g.catalog),''), "
                    "'source_system', 'fec_bulk', "
                    "'synced_at', to_char(g._synced_at, 'YYYY-MM-DD\"T\"HH24:MI:SSZ')))"
                )

                self.stdout.write(f"[{key}] gold.{table} -> Attestation(fec, {subtype}) …")
                cur.execute(f"""
                    INSERT INTO sw_attestation
                        (data_source, jurisdiction_level, jurisdiction_state, source_record_id,
                         entity_uuid, entity_id, entity_subtype, attestation_kind,
                         attested_values, attested_values_hash, attested_at, attested_by,
                         attestation_source_tier, sequence, is_canonical, created_at, updated_at)
                    SELECT '{ds}', '', '', trim({src}),
                           {own_uuid}, {entity_id}, '{subtype}', 'fec',
                           {attested_values}, md5(({attested_values})::text),
                           (g._synced_at at time zone 'UTC'), NULL,
                           'unknown', 0, true, now(), now()
                    FROM gold.{table} g
                    WHERE {where}
                    ON CONFLICT (entity_uuid) DO UPDATE SET
                        attested_values = EXCLUDED.attested_values,
                        attested_values_hash = EXCLUDED.attested_values_hash,
                        attested_at = EXCLUDED.attested_at,
                        attestation_source_tier = EXCLUDED.attestation_source_tier,
                        updated_at = now()
                """)
                self.stdout.write(self.style.SUCCESS(f"[{key}] {cur.rowcount} canonical attestations"))

        self.stdout.write(self.style.SUCCESS("Attestation load complete."))
