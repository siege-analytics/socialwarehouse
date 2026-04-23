# SW PostGIS + AGE image
# Extends postgis/postgis:17-3.5 with Apache AGE 1.6.0 (PG17 build).
# AGE requires shared_preload_libraries='age' — handled via postgresql.conf.age below.

ARG POSTGIS_BASE=postgis/postgis:17-3.5
FROM ${POSTGIS_BASE}

ARG AGE_VERSION=1.6.0
ARG DEBIAN_FRONTEND=noninteractive

# Build, install, and purge build deps in one layer to minimise image size.
# Downloads from downloads.apache.org (GitHub release URL 404s for this tag).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-17 \
        flex \
        bison \
        wget \
    && wget -qO /tmp/age.tar.gz \
        "https://downloads.apache.org/age/PG17/${AGE_VERSION}/apache-age-${AGE_VERSION}-src.tar.gz" \
    && wget -qO /tmp/age.tar.gz.sha512 \
        "https://downloads.apache.org/age/PG17/${AGE_VERSION}/apache-age-${AGE_VERSION}-src.tar.gz.sha512" \
    && sha512sum -c /tmp/age.tar.gz.sha512 \
    && tar -xzf /tmp/age.tar.gz -C /tmp/ \
    && cd /tmp/apache-age-${AGE_VERSION} \
    && make \
    && make install \
    && rm -rf /tmp/age* \
    && apt-get purge -y build-essential postgresql-server-dev-17 flex bison wget \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY postgresql.conf.age /tmp/age.conf
# postgres user owns the config sample; append as root then revert ownership
RUN cat /tmp/age.conf >> /usr/share/postgresql/postgresql.conf.sample
