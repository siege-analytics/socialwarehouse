# socialwarehouse.settings (Django settings module)

**Definition:** `socialwarehouse/settings/base.py` (+ `development.py`, `production.py`, `test.py`)
**Surveyed at:** 2026-05-18 (seeded via survey-context NO-DOC path during ST1 SECRET_KEY hardening)
**Owner:** ops / infra maintainers

## Shape

Per-environment Django settings split. `base.py` declares the shared defaults; `development.py`, `production.py`, `test.py` import-everything from base and override the environment-specific knobs.

| File | Purpose | Notable overrides |
|---|---|---|
| `base.py` | shared defaults | `INSTALLED_APPS`, `MIDDLEWARE`, `DATABASES["default"]` from env vars, GST integration constants |
| `development.py` | dev | `DEBUG = True`, `ALLOWED_HOSTS = ["*"]` |
| `production.py` | prod | `DEBUG = False`, `ALLOWED_HOSTS` from env var |
| `test.py` | CI / local test | override `DATABASES` to `test_socialwarehouse` |

## Required environment variables

| Variable | Used by | Default if unset | Fail-fast? |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | base.py | None — **required in production** (ST1 fix) | **YES (production only)** — KeyError at startup |
| `POSTGRES_DB` | base.py, test.py | `"socialwarehouse"` (base) / `"test_socialwarehouse"` (test) | No |
| `POSTGRES_USER` | base.py | `"socialwarehouse"` | No |
| `POSTGRES_PASSWORD` | base.py (dev fallback), production.py (required) | `""` (dev only — base.py) | **YES (production only)** — KeyError at startup (ST4 fix) |
| `POSTGRES_HOST` | base.py | `"localhost"` | No |
| `POSTGRES_PORT` | base.py | `"5432"` | No |
| `ALLOWED_HOSTS` | production.py | None — **required in production** (ST2 fix); blanks are filtered, all-blank raises RuntimeError | **YES (production only)** — KeyError or RuntimeError at startup |
| `CELERY_BROKER_URL` | base.py | `"redis://localhost:6379/0"` | No |
| `CELERY_RESULT_BACKEND` | base.py | `"redis://localhost:6379/0"` | No |

## INSTALLED_APPS

Order-sensitive (Grappelli must precede `django.contrib.admin`):
- `grappelli`
- Django core: `admin`, `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`, `gis`
- 3rd party: `rest_framework`, `rest_framework_gis`
- SU geo: `siege_utilities.geo.django`
- SW apps: `socialwarehouse.geo`, `socialwarehouse.warehouse`
- GST: `locations` (bare-name; sys.path wired in `base.py` itself post-ST3 / SW#141 so every entry point gets it)

## GST integration constants

Mirrored from upstream GST settings so SW doesn't pull GST's full config (which conflicts):
- `_GST_DATA_DIR`, `SPATIAL_DATA_SUBDIRECTORY`, ..., `NECESSARY_PATHS`
- `DEFAULT_PROJECTION_NUMBER = 4326`
- `PREFERRED_PROJECTION_FOR_US_DISTANCE_SEARCH = 5070`
- `NOMINATIM_API_BASE_URL`, `NOMINATIM_USER_AGENT`, etc.
- `VALID_VECTOR_FILE_EXTENSIONS`

## Known assumptions / gotchas

- **`SECRET_KEY` MUST be set in production via `DJANGO_SECRET_KEY` env var.** Post-ST1/SW#139 fix: `production.py` does `SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]` which raises `KeyError` at startup if unset. `base.py` retains a documented dev-only fallback for local development. Production deployments that forget the env var **fail fast** rather than silently using the insecure default. (Was ST1, fixed.)
- **`POSTGRES_PASSWORD` is required in production.** Post-ST4/SW#142 fix: `production.py` overrides `DATABASES["default"]["PASSWORD"]` with `os.environ["POSTGRES_PASSWORD"]` (KeyError at startup if unset). `base.py` retains the empty-string default for dev. The `S3_ACCESS_KEY` / `S3_SECRET_KEY` in `delta/config.py` (D5) is the same anti-pattern but separate scope. (Was ST4, fixed.)
- **`ALLOWED_HOSTS` is required in production with blank-filtering.** Post-ST2/SW#140 fix: `production.py` does `[h.strip() for h in os.environ["ALLOWED_HOSTS"].split(",") if h.strip()]` — KeyError if env var missing, RuntimeError if it parses to no hosts (e.g. empty string or only commas). Pre-fix returned `[""]` and surfaced as confusing DisallowedHost on every request. (Was ST2, fixed.)
- **`"locations"` in INSTALLED_APPS requires the GST app dir on sys.path.** Post-ST3/#141 fix: `base.py` inserts `vendor/geodjango_simple_template/app/hellodjango` into `sys.path` at module-load time, so every entry point that imports settings (manage.py, wsgi.py, asgi.py, pytest, direct `from socialwarehouse.settings import ...`) gets the wiring. Pre-fix the insert lived only in `manage.py`; any non-manage entry point hit `ModuleNotFoundError: No module named 'locations'` at startup. `manage.py`'s insert is preserved as defense-in-depth but is no longer load-bearing.
- **Settings split via wildcard import** (`from .base import *`). Override files don't re-import `os` explicitly — `production.py` uses `os.environ` through the wildcard import (with `# noqa: F405`). Brittle if `os` is removed from base.py.

## Callers / consumers

- Django process startup reads via `DJANGO_SETTINGS_MODULE` env var (defaults: `development`, `production`, `test`).
- `manage.py` selects the module at command time.
- GST modules (`vendor/geodjango_simple_template/...`) read the GST-mirrored constants directly.

## Cross-references

- `delta/config.py` — Spark settings; separate from Django settings but shares the empty-string-default-for-credentials anti-pattern (D5).
- GST submodule under `vendor/geodjango_simple_template/` — sources the GST integration constants.

## Survey log

- 2026-05-18: Seeded via survey-context NO-DOC path during ST1 / SW#139 fix. Documents the post-ST1 fail-fast pattern for `SECRET_KEY` in production. Pre-ST1 behavior was a hardcoded `"insecure-dev-key-change-in-production"` default in `base.py` that production deployments silently inherited when the env var was unset.
- 2026-05-18: ST2 / SW#140 + ST4 / SW#142 — production.py now fail-fast on missing `ALLOWED_HOSTS` (KeyError, or RuntimeError if env var parses to no hosts) and missing `POSTGRES_PASSWORD` (KeyError). Same shape as ST1 — bracket subscript at the production override layer; base.py retains dev fallbacks.
- 2026-05-19: ST3 / SW#141 — GST sys.path wiring moved from `manage.py` to `base.py` at module-load time. Every entry point that loads settings (wsgi/asgi/pytest/direct-import/manage) gets the wiring, not just manage.py. `manage.py`'s insert preserved as defense-in-depth but no longer load-bearing.
