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

### Quick path (recommended)

```bash
# 1. Clone
git clone https://github.com/siege-analytics/socialwarehouse.git
cd socialwarehouse

# 2. Virtual env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

# 3. Initialize — generates .env with SECRET_KEY and DB credentials
swh init myproject

# 4. Database
createdb socialwarehouse_dev
psql socialwarehouse_dev -c "CREATE EXTENSION postgis;"

# 5. Migrate
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser

# 7. Verify environment
swh doctor
```

### Manual path

If you prefer to configure `.env` manually:

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
swh seed

# Smaller dev runs:
swh seed --state RI                  # Rhode Island
swh seed --state 11                  # DC

# Multi-state:
swh seed --state 48,06,36           # TX + CA + NY

# Skip domains you don't need yet:
swh seed --state 48 --skip economic,civic

# See what would run without doing it:
swh seed --dry-run
```

The `swh seed` command wraps `manage.py seed_demo`; both interfaces are supported:

```bash
# These are equivalent:
swh seed --state 48
python manage.py seed_demo --states 48
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

- **Customize for your jurisdiction.** Set `SW_PROJECT_NAME` in `.env` to your project's identifier (`manage.py template_init` writes this for you). The Django package directory stays as `socialwarehouse/`, so upstream merges keep working; the project-friendly name surfaces in admin labels, dashboards, and operator-facing strings. If you genuinely need a renamed Django package, see ["Renaming the Django package (advanced)"](#renaming-the-django-package-advanced) below.
- **Add an ingest path for a data source we don't ship.** Use D/E/F's existing patterns as the template — each domain's `services/` and `management/commands/` directories show the shape.
- **Bring your own boundary types.** SU's `geo.django.models.*` is the upstream home for new boundary models; SW adds the `{type}_geoid` cache field on Address + ABP.
- **Cron a TIGER vintage refresh.** SU ships `siege_utilities.geo.providers.CensusTIGERProvider.list_available_vintages()` and `siege_utilities.geo.census.tiger_state.check_for_updates(state_file)` for "is a new TIGER vintage published?" checks. Wire those into your scheduler; on a "yes," call `CensusTIGERProvider.get_boundary(...)` for the levels you want. (SW used to ship `scripts/fetch_census_tiger.py` for this; deleted in favor of the SU helpers.)
- **Plan for production scale.** When your database outgrows the single-node dev setup, see [`docs/production-operations.md`](production-operations.md) for the operational decisions you'll need to make — HA topology, backup, connection pooling, partitioning, and more.

## Fork-and-rename ergonomics

For forkers building their own civic / electoral / domain warehouse on top of SW, almost everything customizes via configuration — not by renaming the Python package. The supported customizations:

| Customization | Mechanism | Effort |
|---|---|---|
| Project-friendly name (admin / dashboards) | `SW_PROJECT_NAME` env var (set by `template_init`) | trivial |
| Default seed states | `SW_DEFAULT_STATES` env var; `seed_demo --states` | trivial |
| Postgres DB name + user | `POSTGRES_DB` / `POSTGRES_USER` env vars | trivial |
| Census API key | `CENSUS_API_KEY` env var | trivial |
| Warehouse storage root | `SW_WAREHOUSE_ROOT` env var (file:// for local, s3a:// for cloud) | trivial |
| Add a new domain (school / health / civic-engagement) | Copy the `socialwarehouse/<domain>/` app pattern (services / models / commands) | medium |
| Add a new boundary type | Add the `{type}_geoid` cache field on Address + ABP; register in `_BOUNDARY_TYPES` | medium |
| Replace a vendor data source | Implement the vendor adapter under `swh/voters/<vendor>/` per the documented contract in `docs/entities/voter-file-ingest.md` | medium |

Everything in this table works WITHOUT renaming the `socialwarehouse` Python package. Upstream merges from siege-analytics/socialwarehouse keep working because import paths haven't moved.

### Renaming the Django package (advanced)

Only do this if your project genuinely needs a different module name (e.g. for trademark / namespacing / public-facing-API reasons). The cost is real:

- **Every upstream change to `socialwarehouse.*` imports requires manual re-mapping** when you merge. Tools like `git merge` will not auto-resolve module-rename diffs; you'll see large conflict blocks on every import-edit upstream.
- **Migration history annotation**: Django migrations carry app labels in their state files. Renaming an app (e.g. `sw_geo` → `myproject_geo`) requires either squashing migrations + dropping the old app's migration history, or shipping stub migrations that bridge the old label to the new one. The Django docs cover this; it's a meaningful one-time investment.
- **Coordinating with siege_utilities**: SU ships geographic models that SW extends. The SU integration depends on Django app labels; if you rename SW's apps you'll need to verify SU's models still resolve correctly against your renamed targets.

If you've accepted those costs, the rename recipe:

```bash
# 1. Pick the new package name (e.g. "myproject"). Choose carefully —
# changing it again later compounds the upstream-merge cost.
NEW_NAME=myproject

# 2. Rename the package directory.
git mv socialwarehouse "$NEW_NAME"

# 3. Update every import-from / from-import / app-config reference.
# This is mechanical sed but touches ~92 Python files. Review each one.
grep -rl "socialwarehouse\." --include="*.py" | xargs sed -i.bak \
  "s/from socialwarehouse\./from $NEW_NAME./g; s/import socialwarehouse\./import $NEW_NAME./g"
find . -name "*.bak" -delete

# 4. Update Django app labels in <app>/apps.py. Each is currently "sw_*"
# (e.g. sw_geo, sw_warehouse). Decide if your project keeps the sw_
# prefix or moves to a new one; if changing, ALSO update every existing
# migration's app_label reference + every model's Meta.app_label if set.

# 5. Update INSTALLED_APPS in <new_name>/settings/base.py to match.

# 6. Update setup-time references: pyproject.toml [project] name,
# manage.py DJANGO_SETTINGS_MODULE default, any Docker compose service
# names that reference socialwarehouse.

# 7. Squash or stub-migrate the renamed apps to fix migration state.
# See https://docs.djangoproject.com/en/5.2/topics/migrations/#migration-files
# for the squashmigrations recipe.

# 8. Run the full test suite. Expect ~5-10 import errors on first run;
# fix them iteratively.
python manage.py test
```

Pre-rename: confirm you've actually outgrown the env-var customization path above. The cost of renaming compounds with every upstream merge; the cost of keeping the package name is zero.

## References

- Template-readiness initiative: [#189](https://github.com/siege-analytics/socialwarehouse/issues/189)
- G design (merged): [#211](https://github.com/siege-analytics/socialwarehouse/pull/211)
- Initiative entity docs: `docs/entities/`
- Fork-and-rename audit: [#267](https://github.com/siege-analytics/socialwarehouse/issues/267)
