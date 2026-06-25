# edoburu retagged its images to the v{version}-p{patch} scheme and deleted the
# bare `1.23.1` tag from Docker Hub, which broke `docker compose build`.
# v1.23.1-p3 is the same pgbouncer 1.23.1 in the current tag format, but the
# hardened base differs from the old tag in two ways this image must adapt to:
#   - it runs as non-root (uid 70 postgres) and pgbouncer refuses to run as
#     root, so the entrypoint must stay non-root at runtime;
#   - it drops gettext, but the entrypoint needs envsubst to render the config.
FROM edoburu/pgbouncer:v1.23.1-p3

# Build-time steps need root: install envsubst, stage the entrypoint, and make
# /etc/pgbouncer writable by the postgres user the container runs as.
USER root
RUN apk add --no-cache gettext

COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /etc/pgbouncer \
    && chown -R postgres:postgres /etc/pgbouncer

# Runtime must be non-root (pgbouncer aborts as root).
USER postgres

ENTRYPOINT ["/entrypoint.sh"]
