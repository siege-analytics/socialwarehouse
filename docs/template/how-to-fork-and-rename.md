# How to fork and rename SocialWarehouse

This is the **manual** fork+rename procedure for instance projects today. An automated `template_init` mechanism is designed in [`docs/designs/template-g-quickstart-and-init.md`](../designs/template-g-quickstart-and-init.md) but not yet shipped; when it lands, prefer it over the manual flow. Until then, this doc is the canonical path.

## TL;DR

1. Fork SW on GitHub or clone-then-rename locally.
2. Rename the package (`socialwarehouse` → `<your-warehouse>`) in 12 files (listed below).
3. Rename Django apps if you want different app labels (optional).
4. Update `pyproject.toml`, `.env.example`, settings, and Makefile.
5. Run migrations + seed; verify the dev server starts.
6. Commit + push to your instance project's repo.

Budget: **2-3 hours** end-to-end on a clean dev machine. The package rename is mechanical but spans enough files that you want a working set of `sed` invocations + a careful review pass.

## Step 0 — Decide on a name, structure, and upstream relationship

Before any commands:

- **Pick the Python package name.** Lowercase, underscores not hyphens. Examples: `ukwarehouse`, `eu_demographic_warehouse`, `pa_civic_warehouse`. Avoid `social-` prefix unless your project is also social-data-shaped — generic naming is fine.
- **Decide on Django app prefix.** SW uses `sw_geo`, `sw_warehouse`, etc. (set via `app_label` in each app's `apps.py`). Pick a 2-3 letter prefix for your instance: `uk_geo`, `eu_geo`, etc. This avoids collisions if your project later imports SW alongside.
- **Decide on the upstream-tracking strategy:**
  - **Hard fork** (no upstream connection) — simplest, but you lose access to upstream improvements
  - **Soft fork with periodic upstream merges** — recommended; see [how-to-upgrade-from-upstream.md](how-to-upgrade-from-upstream.md)
  - **Vendored as submodule** — possible but awkward; not recommended for the core warehouse

For most cases: **soft fork with periodic upstream merges**. Add SW as an `upstream` remote (`git remote add upstream git@github.com:siege-analytics/socialwarehouse.git`) so you can pull improvements when ready.

## Step 1 — Clone and initialize your repo

```bash
# Option A: GitHub fork-then-clone
gh repo fork siege-analytics/socialwarehouse --clone --remote
mv socialwarehouse <your-warehouse>
cd <your-warehouse>

# Option B: Plain clone + rename + new remote
git clone git@github.com:siege-analytics/socialwarehouse.git <your-warehouse>
cd <your-warehouse>
git remote rename origin upstream
git remote add origin git@github.com:<your-org>/<your-warehouse>.git
```

## Step 2 — Rename the Python package

```bash
# Rename the package directory
git mv socialwarehouse <your-warehouse>

# Find every file referencing the old name (excluding .git and vendor/)
grep -rln 'socialwarehouse' --exclude-dir=.git --exclude-dir=vendor

# At time of writing, ~25 files reference 'socialwarehouse'. Replace them
# with sed (or your editor's project-wide replace):
LC_ALL=C find . -type f \
  \( -name '*.py' -o -name '*.toml' -o -name '*.cfg' -o -name '*.md' \
  -o -name '*.yml' -o -name '*.yaml' -o -name '*.env*' -o -name 'Makefile' \) \
  -not -path './.git/*' -not -path './vendor/*' \
  -exec sed -i.bak 's/socialwarehouse/<your-warehouse>/g' {} \;

# Verify and remove the .bak files
find . -name '*.bak' -delete

# Sanity-check the rename
grep -rln 'socialwarehouse' --exclude-dir=.git --exclude-dir=vendor
# Should return nothing (or only legitimate references like git submodule URLs)
```

**Files that must end up renamed:**

| File | What changes |
|---|---|
| `pyproject.toml` | `[project] name`, `[tool.setuptools.packages.find] include` |
| `<your-warehouse>/settings/base.py` | `WSGI_APPLICATION`, `ROOT_URLCONF`, app labels in `INSTALLED_APPS` |
| `<your-warehouse>/settings/{dev,prod,test}.py` | Settings module references |
| `<your-warehouse>/wsgi.py`, `asgi.py`, `urls.py`, `celery_app.py` | Package-internal imports |
| `<your-warehouse>/manage.py` | `DJANGO_SETTINGS_MODULE` default |
| `<your-warehouse>/{geo,warehouse,api,civic,demographic,economic,delta,orchestration}/**/*.py` | Cross-app imports |
| `Makefile` | `PYTHONPATH` references |
| `docker-compose.yml` + `docker/*.yml` | Service names + env vars |
| `.env.example` | `DJANGO_SETTINGS_MODULE` |
| `conftest.py` | `DJANGO_SETTINGS_MODULE` |
| `README.md` + `CLAUDE.md` + `docs/**/*.md` | All textual references |
| `pytest.ini_options` (in `pyproject.toml`) | `DJANGO_SETTINGS_MODULE` |

The trickiest is `INSTALLED_APPS` — Django apps are referenced via their `app_label`, not their module name. If you want different app labels (e.g. `uk_geo` instead of `sw_geo`), update each app's `apps.py` `name` and `label`, then update all `app_label.ModelName` references.

If you keep the SW app labels (`sw_geo`, etc.), `INSTALLED_APPS` doesn't need changes beyond the module-path rename.

## Step 3 — Rename Django apps (optional but recommended)

If you want `your_prefix_geo` instead of `sw_geo`:

```python
# <your-warehouse>/geo/apps.py
class GeoConfig(AppConfig):
    name = "<your-warehouse>.geo"
    label = "ukgeo"   # was "sw_geo"
```

Then update every `'sw_geo'` reference (model lookups, migrations, queries) to `'ukgeo'`. This is a one-time pain; afterwards your fork is fully namespace-separated from upstream.

For Django migrations to handle the label change cleanly, you may need to:

1. Squash existing migrations into a single initial migration with the new label
2. Or write a `RenameApp` data migration

The cleanest path is option 1 if you're forking before going to production. If you've already got data in a deployed SW instance, option 2 is required and warrants its own pre-author inventory ticket.

## Step 4 — Reset migrations (optional)

Forking with a clean migration history makes the long-term upgrade story (see [how-to-upgrade-from-upstream.md](how-to-upgrade-from-upstream.md)) easier:

```bash
# Delete existing migrations
find <your-warehouse> -path '*/migrations/*.py' \
  -not -name '__init__.py' -delete

# Generate fresh initial migrations
python manage.py makemigrations
```

This loses git blame on migration files. If that matters, skip this step and live with the longer migration history.

## Step 5 — Configure your `.env`

```bash
cp .env.example .env
```

Edit `.env` to set:

```env
DJANGO_SETTINGS_MODULE=<your-warehouse>.settings.dev
DJANGO_SECRET_KEY=<generate-via-python-secrets-token_urlsafe>
DATABASE_URL=postgres://localhost/<your_warehouse_dev>
SW_WAREHOUSE_ROOT=file:///tmp/<your-warehouse>
SW_CATALOG=<your_warehouse>
SW_VINTAGE=2020   # or whatever your geography's primary vintage is
```

The `SW_*` env vars are namespaced for cross-instance clarity even though SW is renamed — they refer to the warehouse contract, not the package name. Keep them as `SW_*` so the orchestration resources work without per-instance code changes.

## Step 6 — Migrate and seed

```bash
# Create the database
createdb <your_warehouse_dev>
psql <your_warehouse_dev> -c "CREATE EXTENSION postgis;"

# Apply migrations
python manage.py migrate

# Create a superuser for the admin
python manage.py createsuperuser

# Seed minimal demo data (if SW's seed_demo command exists yet — see SW#195)
python manage.py seed_demo --state RI
```

If your instance is non-US, `seed_demo --state RI` won't work — you'll need to author your own per-region seed command following the SW pattern. Track that in your instance project's issue tracker.

## Step 7 — Verify the dev server

```bash
python manage.py runserver
# Open http://localhost:8000/admin/ — log in with the superuser
# Open http://localhost:8000/api/ — DRF browsable API root
```

If everything responds: your fork is bootstrapped.

If you get `ModuleNotFoundError` for old `socialwarehouse.*` imports, grep again — you missed a rename.

## Step 8 — Commit + push to your instance project's repo

```bash
git add -A
git commit -m "feat: rename socialwarehouse -> <your-warehouse> (template fork)"
git push -u origin main   # or develop, depending on your branch convention
```

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'socialwarehouse'` after rename | Missed a rename | `grep -rln 'socialwarehouse' --exclude-dir=.git --exclude-dir=vendor` and finish the pass |
| Django migrations fail with `LookupError: No installed app with label 'sw_geo'` | Renamed app labels but didn't update fixtures / migrations referencing them | Either don't rename app labels (Step 3 is optional) or write the RenameApp migration |
| `pip install -e .` fails | `pyproject.toml` rename was incomplete | Check `[project] name` AND `[tool.setuptools.packages.find] include` |
| Imports work but Dagster doesn't discover assets | `dagster dev -m socialwarehouse.orchestration` still references old name | Use `-m <your-warehouse>.orchestration` |

## What's next

After the fork+rename lands:

- **Swap geography** if your instance is non-US — see [how-to-swap-geography.md](how-to-swap-geography.md)
- **Add domains** SW doesn't ship — see [how-to-add-a-new-domain.md](how-to-add-a-new-domain.md)
- **Set up the upstream-tracking workflow** so you can absorb SW improvements — see [how-to-upgrade-from-upstream.md](how-to-upgrade-from-upstream.md)
- **Extend the Dagster orchestration** with your domain assets — see [`../orchestration/instance-project-guide.md`](../orchestration/instance-project-guide.md)

## See also

- [README.md](README.md) — template overview
- [`docs/designs/template-g-quickstart-and-init.md`](../designs/template-g-quickstart-and-init.md) — the design for the automated init mechanism (when shipped, supersedes this manual flow)
- [`docs/quickstart.md`](../quickstart.md) — the standard quickstart for running SW as-is (US-default; useful as a sanity check before forking)
