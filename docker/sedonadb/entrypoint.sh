#!/usr/bin/env bash
#
# SedonaDB JupyterLab entrypoint.
# Local-dev shape: no token, no password, listens on 0.0.0.0.

set -euo pipefail

PORT="${SEDONADB_PORT:-8889}"

echo "Starting JupyterLab with SedonaDB on port ${PORT}"
echo "Access at: http://localhost:${PORT}"
echo ""
echo "Quickstart in a notebook:"
echo "  import sedona.db"
echo "  con = sedona.db.connect()"
echo "  con.sql(\"SELECT ST_Point(1, 2)\").show()"
echo ""

exec jupyter lab \
    --ip=0.0.0.0 \
    --port="${PORT}" \
    --no-browser \
    --allow-root \
    --ServerApp.token='' \
    --ServerApp.password='' \
    --ServerApp.disable_check_xsrf=True
