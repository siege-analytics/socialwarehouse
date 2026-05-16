#!/usr/bin/env bash
#
# Generate GitHub Wiki content from templates in scripts/wiki-templates/.
# Reads .env for substitution values, writes output to wiki/.
#
# Usage:
#   bash scripts/generate-wiki.sh
#
# Then push to the GitHub Wiki:
#   git clone git@github.com:siege-analytics/socialwarehouse.wiki.git
#   cp wiki/* socialwarehouse.wiki/
#   cd socialwarehouse.wiki && git add -A && git commit -m "..." && git push
#
# (CI-driven push to wiki repo is a separate follow-up.)

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
TEMPLATE_DIR="$SCRIPT_DIR/wiki-templates"
OUT_DIR="$REPO_ROOT/wiki"

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "ERROR: template directory not found: $TEMPLATE_DIR" >&2
    exit 1
fi

# Load .env if present. Tolerate its absence -- defaults below cover the
# placeholder substitutions, and a wiki regen against a fresh checkout
# (no .env yet) should still produce sensible output.
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^[[:space:]]*#' "$REPO_ROOT/.env" | grep -v '^[[:space:]]*$')
    set +a
fi

# Defaults match .env.example so wiki generation works against a fresh
# checkout. Anything sensitive (passwords, tokens) stays placeholder-only
# -- the wiki should never carry real credentials.
PROJECT_NAME="${PROJECT_NAME:-Social Warehouse}"
POSTGRES_HOST="${POSTGRES_HOST:-postgis}"
POSTGRES_USER="${POSTGRES_USER:-socialwarehouse}"
POSTGRES_DB="${POSTGRES_DB:-gis}"
POSTGRES_PORT="${POSTGRES_PORT:-54324}"
NEO4J_HEAP="${NEO4J_HEAP:-512m}"
NEO4J_PAGECACHE="${NEO4J_PAGECACHE:-512m}"
DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-socialwarehouse.settings.development}"
CENSUS_YEAR="${CENSUS_YEAR:-2023}"
CENSUS_CONGRESS_NUMBER="${CENSUS_CONGRESS_NUMBER:-118}"

# Sentinel for any password reference in the templates -- the wiki should
# never publish real values.
WIKI_PASSWORD_PLACEHOLDER="see .env (CHANGEME)"

export PROJECT_NAME POSTGRES_HOST POSTGRES_USER POSTGRES_DB POSTGRES_PORT \
       NEO4J_HEAP NEO4J_PAGECACHE DJANGO_SETTINGS_MODULE \
       CENSUS_YEAR CENSUS_CONGRESS_NUMBER WIKI_PASSWORD_PLACEHOLDER

mkdir -p "$OUT_DIR"

generated=0
for tpl in "$TEMPLATE_DIR"/*.md; do
    [ -f "$tpl" ] || continue
    name="$(basename "$tpl")"
    out="$OUT_DIR/$name"
    envsubst < "$tpl" > "$out"
    echo "  generated wiki/$name"
    generated=$((generated + 1))
done

echo ""
echo "Generated $generated wiki page(s) under $OUT_DIR"
echo ""
echo "Next: push to https://github.com/siege-analytics/socialwarehouse.wiki.git"
echo "(Manual for now -- CI-driven push is a follow-up.)"
