# survey-context project skill — socialwarehouse

## Doc root

`docs/entities/` (relative to repo root)

## Entity catalog

| Name | Type | Namespace | Doc page |
|---|---|---|---|
| DimGeography | Django model | socialwarehouse.warehouse.models | docs/entities/dim_geography.md |
| DimTime | Django model | socialwarehouse.warehouse.models | docs/entities/dim_time.md |
| DimRedistrictingCycle | Django model | socialwarehouse.warehouse.models | docs/entities/dim_redistricting_cycle.md |
| Address | Django model | socialwarehouse.geo.models | docs/entities/address.md |
| DemographicSnapshot | Django model | siege_utilities.geo.django.models.demographics | docs/entities/demographic_snapshot.md |
| api/geo views decorators | DRF decorator surface | socialwarehouse.api.geo.views | docs/entities/api_geo_views_decorators.md |
| delta/enrichment.py | Spark module | socialwarehouse.delta.enrichment | docs/entities/delta_enrichment.md |
| delta/config.py | Spark config module | socialwarehouse.delta.config | docs/entities/delta_config.md |
| settings | Django settings module | socialwarehouse.settings | docs/entities/settings.md |
| swh/voters.py | Python module | swh.voters | docs/entities/swh_voters.md |

Seed coverage chosen for E1 hostile-review frequency. Catalog grows on next touch — every `NO-DOC` outcome in survey artifacts is a candidate.

## Ownership

- **Drift findings** file as GitHub issues in `siege-analytics/socialwarehouse`, child of #49 (E1 epic) until E1 closes, then under a dedicated `drift` label.
- **Doc-update DoD** reviewed by the PR author at self-review time (see [`self-review` skill](../../skills/self-review/SKILL.md)); hook enforcement deferred to v2.1.
- **Cross-repo entities** (e.g. DemographicSnapshot lives in siege_utilities): doc page lives here; upstream changes that affect SW callers are recorded in the survey log on the local page.

## Recipe extensions

Project-specific recipes live in `recipes/`. Initial set:

- `recipes/census-vintage.md` — TIGER vintage handling, summary_level conventions, geoid-vs-fips-vs-id distinctions.
- `recipes/django-orm-defaults.md` — `update_or_create(defaults={...})` kwarg validation against Model._meta (mirrors the static scanner at claude-configs-public#117).

## Notes

This is the seed project-skill landing alongside global survey-context v2. Bootstrap is intentionally narrow — 6 entities chosen to ground the contract concretely. Coverage grows organically through the skill's `NO-DOC → seed` path.
