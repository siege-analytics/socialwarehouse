# Configuration

`${PROJECT_NAME}` reads its configuration from `.env` (copied from `.env.example` on first setup). All sensitive values use `CHANGEME` placeholders -- replace them before bringing up services.

## Environment variables

### PostgreSQL / PostGIS

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_HOST` | `${POSTGRES_HOST}` | docker-compose service name |
| `POSTGRES_DB` | `${POSTGRES_DB}` | warehouse database |
| `POSTGRES_USER` | `${POSTGRES_USER}` | application user |
| `POSTGRES_PASSWORD` | `CHANGEME` | ${WIKI_PASSWORD_PLACEHOLDER} |
| `POSTGRES_HOST_AUTH_METHOD` | `scram-sha-256` | |
| `POSTGRES_PORT` | `${POSTGRES_PORT}` | host-side mapped port |

### Docker build

| Variable | Default |
|---|---|
| `UBUNTU_BASE_IMAGE` | `ubuntu:24.04` |
| `PYTHON_VENV_PATH` | `/opt/venv` |

### Spark

| Variable | Default | Notes |
|---|---|---|
| `SPARK_NO_DAEMONIZE` | `true` | required for proper container shutdown |

### Django

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `${DJANGO_SETTINGS_MODULE}` | dev/prod/test variants |
| `DJANGO_SECRET_KEY` | `local-dev-insecure-do-not-deploy` | rotate for any non-local environment |

### Celery

| Variable | Default |
|---|---|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` |

### Neo4j

| Variable | Default | Notes |
|---|---|---|
| `NEO4J_HEAP` | `${NEO4J_HEAP}` | heap memory |
| `NEO4J_PAGECACHE` | `${NEO4J_PAGECACHE}` | page cache |
| `NEO4J_PASSWORD` | `CHANGEME` | ${WIKI_PASSWORD_PLACEHOLDER} |

### Census data (used by `swh` CLI)

| Variable | Default |
|---|---|
| `CENSUS_YEAR` | `${CENSUS_YEAR}` |
| `CENSUS_CONGRESS_NUMBER` | `${CENSUS_CONGRESS_NUMBER}` |
| `CENSUS_STATES` | `all` |

## Services and ports

| Service | Port (host) | Notes |
|---|---|---|
| PostGIS | `${POSTGRES_PORT}` | application warehouse |
| Spark Master UI | `9090` | when `make up-spark` profile is active |
| Spark History | `18080` | when `make up-spark` profile is active |
| Django | depends on profile | usually fronted by gunicorn / nginx |
| Neo4j Browser | `7474` | when Neo4j service is up |
| Neo4j Bolt | `7687` | application connections |

## Profiles

`make up` -- PostGIS + Python container (minimal).
`make up-spark` -- adds the Spark cluster (master + worker(s)).
`make up-full` -- everything (Spark + Zeppelin + Maven).

`make down` to stop. `make clean` to also remove volumes.

## Generation

This wiki page is generated from `scripts/wiki-templates/Configuration.md` by `scripts/generate-wiki.sh`. Update the template, not this page.
