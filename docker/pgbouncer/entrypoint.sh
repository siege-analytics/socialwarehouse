#!/bin/sh
set -e

PGBOUNCER_USER="${POSTGRES_USER:-socialwarehouse}"
PGBOUNCER_PASS="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

mkdir -p /etc/pgbouncer

echo "\"${PGBOUNCER_USER}\" \"${PGBOUNCER_PASS}\"" > /etc/pgbouncer/userlist.txt

envsubst < /etc/pgbouncer/pgbouncer.ini.template > /etc/pgbouncer/pgbouncer.ini

exec pgbouncer /etc/pgbouncer/pgbouncer.ini
