# ${PROJECT_NAME}

Data warehouse for social, civic, and economic data. Built on Spark + PostgreSQL/PostGIS + Neo4j, with a Django web layer pulled in via the `geodjango_simple_template` (GST) submodule.

## What this is

`${PROJECT_NAME}` is a **template** for warehouse projects. It provides:

- A PostGIS-backed star-schema warehouse for geographic + demographic + civic data.
- Spark jobs (Spark 4.1.1 + Sedona 1.9.0) for distributed processing and spatial joins.
- Neo4j as a graph layer for network-shaped queries.
- A Django REST API (via the GST submodule) that serves warehouse content over HTTP.

Instance projects (FEC pipelines, electoral analytics, others) consume this template + add instance-specific transforms.

See [Configuration](Configuration) for environment variable details and [the README](https://github.com/siege-analytics/socialwarehouse) for setup steps.

## Quick start

```bash
git clone --recurse-submodules git@github.com:siege-analytics/socialwarehouse.git
cd socialwarehouse
cp .env.example .env       # edit the CHANGEME values
make up                    # start PostGIS + Python (default profile)
make up-spark              # add Spark cluster
make up-full               # everything (Spark + Zeppelin + Maven)
```

## Stack

| Layer | Technology |
|---|---|
| Distributed processing | Apache Spark 4.1.1 (Scala 2.13.14, Java 21 Temurin) |
| Spatial analytics | Apache Sedona 1.9.0 |
| Warehouse | PostgreSQL 16 + PostGIS |
| Graph | Neo4j 5 Community |
| Application layer | Django + GST submodule |
| Async tasks | Celery + Redis |
| Container OS | Ubuntu 24.04 (Python 3.12) |

## Conventions

- `develop` is the integration branch; `main` is release-cut.
- Direct commits to `main`, `master`, or `develop` are blocked -- use a feature branch + PR.
- Census data context defaults to year ${CENSUS_YEAR}, Congress number ${CENSUS_CONGRESS_NUMBER}.
- Django settings module: `${DJANGO_SETTINGS_MODULE}`.

## Where to look

- [Configuration](Configuration) -- environment variables, services, ports.
- `CLAUDE.md` (in repo root) -- agent-facing project context.
- `README.md` (in repo root) -- human-facing onboarding.
- `docs/` (in repo root) -- topic-specific reference (e.g., zeppelin-jdbc).

## Generation

This wiki page is generated from `scripts/wiki-templates/Home.md` by `scripts/generate-wiki.sh`. To update, edit the template and re-run the generator; do not edit the published wiki page directly (changes will be overwritten on the next regen).
