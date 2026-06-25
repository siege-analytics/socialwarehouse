# edoburu retagged its images to the v{version}-p{patch} scheme and deleted
# the bare `1.23.1` tag from Docker Hub, which broke `docker compose build`.
# v1.23.1-p3 is the same pgbouncer 1.23.1 in the current tag format.
FROM edoburu/pgbouncer:v1.23.1-p3

COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
