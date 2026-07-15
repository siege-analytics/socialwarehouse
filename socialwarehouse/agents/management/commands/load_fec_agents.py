"""Load FEC gold entity dimensions into the SW Agent supertype + subtypes.

Reads the resolved-entity tables in the ``gold`` schema (a verbatim FDW
mirror of ``electinfo.gold``, co-located in electinfo_data_warehouse) and
materializes each resolved entity as a ``core.Agent`` supertype row plus
its typed subtype row (``agents.Committee`` / ``agents.Person`` /
``agents.Organization``), linked by the nullable Agent FK on the subtype
(the #348 supertype/subtype split).

Identity is deterministic UUID5 (``core.mixins.generate_entity_uuid5``):

* Agent.entity_uuid   = uuid5(subtype, data_source, source_id)
  — matches ``Agent.save() -> assign_uuid5(subtype, data_source, source_record_id)``.
* Subtype.entity_uuid = uuid5(data_source, source_id)
  — the subtype's own identity space, wired to the Agent hub by the FK.

Because the normalizer (``normalize_v1``: lower/strip, pipe-join) and the
SW namespace are portable, and Postgres ``uuid_generate_v5`` (uuid-ossp)
implements the same RFC-4122 SHA-1 v5 as Python ``uuid.uuid5``, the whole
load runs as a set-based in-DB ``INSERT...SELECT`` — verified byte-identical
to the Django model logic. This makes both the initial load and the
re-load-on-corrected-gold cheap (seconds/minutes, not hours for 37M).

Idempotent: entity_uuid is unique per table, so ``ON CONFLICT DO NOTHING``
skips rows already present. Load against CURRENT gold now; re-run when
corrected gold lands.

Attestation (gold provenance -> core.FECAttestation) is a SEPARATE loader:
gold entities are resolved aggregates, not FEC forms, so the attestation
shape is under design review. This command loads entity dimensions only.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from socialwarehouse.core.mixins import SW_NAMESPACE

# Each spec drives two set-based inserts (Agent supertype, then typed subtype
# joined back to its Agent by the deterministic entity_uuid). ``src`` is the
# SQL expression for the source identity; ``sub_cols``/``sub_vals`` are the
# type-specific columns beyond the shared identity/audit columns.
SPECS = {
    "committee": dict(
        subtype="committee", ds="fec", table="committee_entities",
        src="g.fec_committee_id", where="g.fec_committee_id is not null and g.fec_committee_id <> ''",
        target="sw_committee",
        sub_cols="name, committee_type, source_system_id, formation_date, termination_date, name_history",
        sub_vals=(
            "coalesce(nullif(trim(g.committee_name),''),'(unnamed committee)'), "
            "coalesce(nullif(trim(g.committee_type),''),'other'), "
            "trim(g.fec_committee_id), g.eff_start_dt, g.eff_stop_dt, '[]'::jsonb"
        ),
    ),
    "candidate": dict(
        subtype="person", ds="fec", table="candidate_entities",
        src="g.fec_candidate_id", where="g.fec_candidate_id is not null and g.fec_candidate_id <> ''",
        target="sw_person",
        sub_cols="full_name, given_name, family_name, middle_name, name_suffix",
        sub_vals=(
            "coalesce(nullif(trim(g.candidate_name),''),'(unnamed)'), "
            "coalesce(trim(g.first_name),''), coalesce(trim(g.last_name),''), '', "
            "coalesce(trim(g.name_suffix),'')"
        ),
    ),
    "officeholder": dict(
        subtype="person", ds="congress", table="officeholder_entities",
        src="g.bioguide_id", where="g.bioguide_id is not null and g.bioguide_id <> ''",
        target="sw_person",
        sub_cols="full_name, given_name, family_name, middle_name, name_suffix, birth_year",
        sub_vals=(
            "coalesce(nullif(trim(g.name),''),'(unnamed)'), "
            "coalesce(trim(g.first_name),''), coalesce(trim(g.last_name),''), '', '', "
            "nullif(regexp_replace(coalesce(g.birth_year,''),'[^0-9]','','g'),'')::smallint"
        ),
    ),
    "individual": dict(
        subtype="person", ds="fec", table="individual_entities",
        src="g.id", where="g.id is not null and g.id <> ''",
        target="sw_person",
        sub_cols="full_name, given_name, family_name, middle_name, name_suffix",
        sub_vals=(
            "coalesce(nullif(trim(g.name),''),'(unnamed)'), '', '', '', ''"
        ),
    ),
    "vendor": dict(
        subtype="organization", ds="fec", table="vendor_entities",
        src="g.id", where="g.id is not null and g.id <> ''",
        target="sw_organization",
        sub_cols="name, industry_code, industry_system",
        sub_vals="coalesce(nullif(trim(g.name),''),'(unnamed org)'), '', 'naics'",
    ),
    "employer": dict(
        subtype="organization", ds="fec", table="employer_entities",
        src="g.id", where="g.id is not null and g.id <> ''",
        target="sw_organization",
        sub_cols="name, industry_code, industry_system",
        sub_vals="coalesce(nullif(trim(g.name),''),'(unnamed org)'), '', 'naics'",
    ),
}

# Only sw_committee carries source_system_id; sw_person / sw_organization use the
# shared source_record_id for source identity. Individuals (37M) load last.
ORDER = ["committee", "candidate", "officeholder", "vendor", "employer", "individual"]


class Command(BaseCommand):
    help = "Load FEC gold resolved entities into Agent supertype + typed subtypes (set-based)."

    def add_arguments(self, parser):
        parser.add_argument("--entity", default="all",
                            choices=["all", *SPECS], help="entity type or 'all'")

    def handle(self, *args, **opts):
        ns = str(SW_NAMESPACE)
        which = ORDER if opts["entity"] == "all" else [opts["entity"]]
        with connection.cursor() as cur:
            for key in which:
                s = SPECS[key]
                src, ds, subtype = s["src"], s["ds"], s["subtype"]
                # Deterministic identity expressions (match generate_entity_uuid5).
                agent_uuid = (
                    f"uuid_generate_v5('{ns}'::uuid, "
                    f"'{subtype}|{ds}|' || lower(trim({src})))"
                )
                sub_uuid = (
                    f"uuid_generate_v5('{ns}'::uuid, "
                    f"'{ds}|' || lower(trim({src})))"
                )

                self.stdout.write(f"[{key}] gold.{s['table']} -> Agent({subtype}) + {s['target']} …")

                # 1) Agent supertype.
                cur.execute(f"""
                    INSERT INTO sw_agent
                        (data_source, jurisdiction_level, jurisdiction_state,
                         source_record_id, entity_uuid, subtype, lifecycle_state,
                         created_at, updated_at)
                    SELECT '{ds}', '', '', trim({src}), {agent_uuid},
                           '{subtype}', 'active', now(), now()
                    FROM gold.{s['table']} g
                    WHERE {s['where']}
                    ON CONFLICT (entity_uuid) DO NOTHING
                """)
                agents = cur.rowcount

                # 2) Typed subtype, linked to its Agent via the deterministic uuid.
                cur.execute(f"""
                    INSERT INTO {s['target']}
                        (data_source, jurisdiction_level, jurisdiction_state,
                         source_record_id, entity_uuid, agent_id, created_at, updated_at,
                         {s['sub_cols']})
                    SELECT '{ds}', '', '', trim({src}), {sub_uuid}, a.id, now(), now(),
                           {s['sub_vals']}
                    FROM gold.{s['table']} g
                    JOIN sw_agent a ON a.entity_uuid = {agent_uuid}
                    WHERE {s['where']}
                    ON CONFLICT (entity_uuid) DO NOTHING
                """)
                subs = cur.rowcount

                self.stdout.write(self.style.SUCCESS(
                    f"[{key}] +{agents} Agent, +{subs} {s['target'].replace('sw_','')} rows"))

        self.stdout.write(self.style.SUCCESS("Entity load complete."))
