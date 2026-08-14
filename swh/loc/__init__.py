"""Library-of-Congress / congress-legislators -> civic-ontology Person ingest (#73).

Turns the public unitedstates/congress-legislators dataset (plus, in
future, LoC Biographical Directory narrative bios and unitedstates/images
portraits) into the existing General Civic Ontology entities:

    Person (Agent subtype)  +  Agent hub  +  EntityIdentifier (bioguide,
    FEC candidate ids, govtrack, ...)  +  a canonical Attestation carrying
    the source record  +  Office / OfficeTerm for congressional service.

Nothing bespoke is introduced — it materializes into the models that
already exist (`socialwarehouse.agents`, `socialwarehouse.core`,
`socialwarehouse.political`). Multi-source bios are the Attestation
pattern: congress-legislators is one attesting source; a narrative
bioguide bio or a pre-Congress business-site bio attach as additional
attestations on the same Person.
"""

from swh.loc import mappings  # noqa: F401
from swh.loc.materialize import materialize_legislators  # noqa: F401

__all__ = ["mappings", "materialize_legislators"]
