# Boundary-Estimation Algorithm: Provenance and Lineage

## Origin

The boundary-estimation technique — using known-boundary addresses to
estimate district boundaries for addresses with uncertain geocodes — is
original Siege Analytics intellectual property, created by Dheeraj Chand.

## The 7-Step PostGIS Pipeline

The algorithm is a reusable primitive that SocialWarehouse's voter-domain
consumers can rely on or extend. The steps:

1. **Copy voter rows** — stage the address set for the target jurisdiction.
2. **Label-spatial-match** — tag each address with the known boundary it
   falls inside (point-in-polygon against authoritative boundaries).
3. **Tabblock join** — associate addresses with Census tabulation blocks
   for spatial grouping.
4. **Neighbor-fill** — propagate boundary assignments from known addresses
   to their spatial neighbors within the same tabulation block.
5. **Union** — merge the assigned tabulation blocks into contiguous
   boundary geometries.
6. **Dump multipolygons** — decompose complex geometries into simple
   polygons for downstream consumption.
7. **Filter** — remove artifacts and validate the estimated boundaries
   against known constraints (area thresholds, topology checks).

Each step is a composable SQL operation against PostGIS. The pipeline
can run against any boundary type where a subset of addresses have
authoritative assignments (e.g., voter-file-reported districts) and
the goal is to estimate boundaries for the remainder.

## Implementation History

| Period | Context | Implementation |
|--------|---------|----------------|
| Original | Siege Analytics | Algorithm designed and prototyped by Dheeraj Chand |
| Advisory period | CiviTech | Deployed as an Airflow DAG on CiviTech infrastructure while Dheeraj served as advisor. The deployment used CiviTech resources; the algorithm remained Siege Analytics IP. |
| Current | Reverberator | Lives in `queries.py` + `run_jobs.py` (legacy) and `src/sql/templates/*.sql` (refactored, step-aligned). Reverberator epic #27 tracks integration with SocialWarehouse as the substrate. |

## Relationship to SocialWarehouse

As SocialWarehouse becomes the boundary-estimation substrate (per
Reverberator epic #27), this algorithm is the core primitive that the
orchestration layer will invoke. The Dagster asset graph for the
electoral/voter domain will wrap these steps as assets in the
bronze→silver→gold pipeline, with each step's PostGIS output registered
as a Delta table for auditability.

The integration shape (shared vs. separate Dagster code location) is
tracked in SW#282.
