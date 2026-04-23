# SW PostGIS + AGE image
# Extends postgis/postgis:17-3.5 with Apache AGE 1.6.0 (PG17 build).
# AGE requires shared_preload_libraries='age' — handled via postgresql.conf.age below.

ARG POSTGIS_BASE=postgis/postgis:17-3.5
FROM ${POSTGIS_BASE}

ARG AGE_VERSION=1.6.0
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-17 \
        flex \
        bison \
        wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN wget -qO /tmp/age.tar.gz \
      "https://github.com/apache/age/releases/download/PG17%2Fv${AGE_VERSION}/apache-age-${AGE_VERSION}-src.tar.gz" \
    && tar -xzf /tmp/age.tar.gz -C /tmp/ \
    && cd /tmp/apache-age-${AGE_VERSION} \
    && make \
    && make install \
    && rm -rf /tmp/age*

RUN apt-get purge -y build-essential postgresql-server-dev-17 flex bison wget \
    && apt-get autoremove -y \
    && apt-get clean

COPY postgresql.conf.age /tmp/age.conf
RUN cat /tmp/age.conf >> /usr/share/postgresql/postgresql.conf.sample
