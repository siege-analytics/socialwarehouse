# SocialWarehouse Quickstart

From `git clone` to a working dev instance with seeded one-state data across all four domains (political, demographic, economic, civic). Target: under 1 hour on a fresh dev machine.

## Prereqs

You'll need:

- **Python 3.11 or later**
- **PostgreSQL 14+** with **PostGIS 3.x** extension
- (Optional) **Redis** for Celery-backed background jobs
- (Optional) A **Census API key** (free; register at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)) — only needed for high-volume ACS pulls; small dev pulls work without

PostGIS install is the long pole — budget ~15-20 minutes on macOS with Homebrew, similar on Ubuntu apt.

### macOS

```bash
brew install postgresql@15 postgis python@3.12 gdal
brew services start postgresql@15
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install postgresql-15 postgresql-15-postgis-3 python3.12 python3.12-venv libgdal-dev
sudo systemctl start postgresql
```

## Setup

```bash
# 1. Clone
git clone https://github.com/siege-analytics/socialwarehouse.git
cd socialwarehouse

# 2. Virtual env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

# 3. Database
createdb socialwarehouse_dev
psql socialwarehouse_dev -c "CREATE EXTENSION postgis;"

# 4. Settings
cp .env.example .env  # if present; otherwise create one with the variables below

# Required variables in .env:
#   DJANGO_SECRET_KEY=<any-random-string-for-dev>
#   POSTGRES_DB=socialwarehouse_dev
#   POSTGRES_USER=<your-system-user>
#   POSTGRES_PASSWORD=
#   POSTGRES_HOST=localhost
#   POSTGRES_PORT=5432
#   SW_WAREHOUSE_ROOT=file:///tmp/sw-warehouse
# Optional:
#   CENSUS_API_KEY=<from api.census.gov/data/key_signup.html>
#   BLS_API_KEY=<from bls.gov/developers/>

# 5. Migrate
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser
```

## Seed data

One command pulls a state's data across all four domains:

```bash
# Default: Texas (per G design Q2 — demographic + economic diversity).
python manage.py seed_demo

# Smaller dev runs:
python manage.py seed_demo --states RI                  # Rhode Island
python manage.py seed_demo --states 11                  # DC

# Multi-state:
python manage.py seed_demo --states 48,06,36           # TX + CA + NY

# Skip domains you don't need yet:
python manage.py seed_demo --states 48 --skip economic,civic

# See what would run without doing it:
python manage.py seed_demo --states 48 --dry-run
```

The `seed_demo` command wraps these per-domain commands; you can run them individually if you want finer control:

- `python manage.py assign_boundaries --year 2020 --state 48` — political
- `python manage.py load_acs --vintage 2019-2023 --state 48 --geography county` — demographic
- `python manage.py load_qcew --vintage 2024Q3 --state 48` — economic
- `python manage.py load_nces --vintage 2022-23 --state 48` — civic (CCD district)
- `python manage.py load_nces_schools --vintage 2022-23 --state 48` — civic (CCD school)
- `python manage.py load_nces_edge --vintage 2022-23 --acs-endpoint 2018-22 --state 48` — civic (EDGE demographics)

## Verify

```bash
python manage.py runserver
```

In another terminal:

```bash
# Hit a boundary lookup — should return a TX boundary.
curl 'http://localhost:8000/api/geo/boundary?type=state&geoid=48'

# Spot-check the ingest in a Django shell.
python manage.py shell
>>> from socialwarehouse.demographic.models import ACSEstimate
>>> ACSEstimate.objects.filter(boundary_type='county', geoid='48201').count()  # Harris County, TX
>>>
>>> from socialwarehouse.economic.models import BLSQCEWAggregate
>>> BLSQCEWAggregate.objects.filter(geoid='48201').count()
>>>
>>> from socialwarehouse.civic.models import NCESDistrictAggregate
>>> NCESDistrictAggregate.objects.filter(state_fips='48').count()
```

## Common problems

**`createdb: error: database "socialwarehouse_dev" already exists`** — drop and recreate, or use a different name in `.env`.

**`psql: error: connection to server on socket... failed: No such file or directory`** — PostgreSQL isn't running. `brew services start postgresql@15` (mac) or `sudo systemctl start postgresql` (linux).

**`CREATE EXTENSION postgis` says "extension postgis is not available"** — PostGIS isn't installed alongside PostgreSQL. On macOS: `brew install postgis`. On Ubuntu: `sudo apt install postgresql-15-postgis-3` (match your Postgres version).

**`No module named 'siege_utilities'`** — `pip install -e .` didn't pick up extras. Try `pip install -e .[geodjango]`.

**`load_acs` returns "Census API returned no rows"** — the variable subset returned no data for the requested geography. Confirm the (state, geography, year) combination is valid; ACS doesn't always publish at every level for every release.

**`load_qcew` 403 / 404** — BLS occasionally reshapes their URLs. Open an issue at [SW#196](https://github.com/siege-analytics/socialwarehouse/issues/196) (CI-hygiene tracking) with the failing URL.

**Migration `0004` complains about missing vintage seeds** — the seed runs as a `RunPython` data migration. If it skipped, run `python manage.py seed_known_vintages` manually.

## What you have after this

You've got:

- A working Django + PostGIS dev instance.
- One state's data populated across all four domains (political boundaries, ACS demographics, BLS employment, NCES schools).
- The Address ⇄ AddressBoundaryPeriod temporal model loaded and the F11 helpers (`boundary_history`, `boundary_on`, `boundary_timeline`, `geoid_on`, `current_geoid`, `current_boundaries`, `boundary_at`) ready to query.
- All four domains' ingest commands available for re-running with different vintages / states / variables.

## What's next

- **Customize for your jurisdiction.** Once `manage.py template_init` lands (G.2, tracked at SW#195), the clone-and-rename step will produce a renamed instance with your project's name + a chosen state subset baked in.
- **Add an ingest path for a data source we don't ship.** Use D/E/F's existing patterns as the template — each domain's `services/` and `management/commands/` directories show the shape.
- **Bring your own boundary types.** SU's `geo.django.models.*` is the upstream home for new boundary models; SW adds the `{type}_geoid` cache field on Address + ABP.
- **Cron a TIGER vintage refresh.** SU ships `siege_utilities.geo.providers.CensusTIGERProvider.list_available_vintages()` and `siege_utilities.geo.census.tiger_state.check_for_updates(state_file)` for "is a new TIGER vintage published?" checks. Wire those into your scheduler; on a "yes," call `CensusTIGERProvider.get_boundary(...)` for the levels you want. (SW used to ship `scripts/fetch_census_tiger.py` for this; deleted in favor of the SU helpers.)

## References

- Template-readiness initiative: [#189](https://github.com/siege-analytics/socialwarehouse/issues/189)
- G design (merged): [#211](https://github.com/siege-analytics/socialwarehouse/pull/211)
- Initiative entity docs: `docs/entities/`
