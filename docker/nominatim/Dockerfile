# Self-hosted Nominatim for the Social Warehouse DSTK-replacement
# geocoding path.
#
# Based on the mediagis/nominatim community image, which bundles
# Nominatim + PostgreSQL + the import tooling. First container boot
# downloads the configured OSM PBF (default: Rhode Island, ~200 MB,
# 10-15 minute import) and produces a ready-to-query Nominatim
# instance.
#
# Loading a different state: set NOMINATIM_PBF_URL in the workspace
# .env, then `make clean-nominatim && make up-nominatim`. The clean
# step deletes the postgres volume so the import re-runs from scratch
# against the new PBF.
#
# See docs/geocoding-self-host.md for the full bootstrap procedure,
# per-state scaling guidance, and smoke-test endpoints.

FROM mediagis/nominatim:5.0

# Healthcheck: the Nominatim status endpoint reports HTTP 200 once
# Postgres is up AND the import has completed at least once. During
# the first-boot import this will fail for ~10-15 minutes for RI
# (longer for larger states); the start-period gives that window.
HEALTHCHECK --interval=30s --timeout=10s --start-period=900s --retries=3 \
  CMD curl -fsS http://localhost:8080/status.php?format=json || exit 1
