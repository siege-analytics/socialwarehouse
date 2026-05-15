#!/usr/bin/env bash
#
# Load TIGER shapefiles into PostGIS.
#
# Reads connection settings from .env -- mirrors the dev/sw.zsh and
# Makefile conventions used elsewhere in the repo. Sample defaults that
# were previously hardcoded here have been removed (#60).
#
# Usage:
#   source <(grep -v '^#' .env | xargs -I {} echo export {})
#   bash code/bash_scripts/load_psql.sh
#
# Or run via Makefile / docker compose where .env is already loaded.

set -euo pipefail

# Connection settings from environment. Fallbacks match docker-compose
# service names so the script also works inside a running container.
export PGHOST="${POSTGRES_HOST:-postgis}"
export PGUSER="${POSTGRES_USER:?POSTGRES_USER must be set (in .env)}"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set (in .env)}"
export PGPORT="${POSTGRES_PORT:-54324}"
export PGDATABASE="${POSTGRES_DB:-gis}"

schema="${LOAD_PSQL_SCHEMA:-public}"
tabblock_projection="${LOAD_PSQL_SRID:-4269}"

SOURCE_DIR='./downloads'
ZIP_DIR="./unzipped"

find ./ -name '*.zip' -exec sh -c 'unzip -u -d "${1%.*}" "$1"' _ {} \;

for shapefile in $(find downloads/ -type f -name '*.shp');
 do
   tablename="$(basename "$shapefile" .shp)"
   echo $tablename
   shp2pgsql -d -I -s $tabblock_projection $shapefile $schema.$tablename | psql
 done
