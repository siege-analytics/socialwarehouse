# socialwarehouse

> **SESSION START**: Read this file, then read the electinfo cross-project docs:
> ```
> ~/git/electinfo/docs/socialwarehouse.md   # Architecture overview
> ~/git/electinfo/CLAUDE.md                  # Cross-project conventions
> ```

## What This Is

Socialwarehouse is a data warehouse and delta lake for geographic, demographic, and civic data. It replaces the Data Science Toolkit (DSTK) with a self-hosted, scalable system.

**siege_utilities** = kitchen equipment — single-serving geographic operations (geocode, boundary lookup, demographics)
**socialwarehouse** = the restaurant — uses SU's verbs to run geocoding, boundary management, and Census warehousing at massive scale
**geodjango_simple_template** (GST) = the dining room template — webapp scaffold pulled in as a git submodule at `vendor/geodjango_simple_template/` (pinned). SW uses GST for the web-app side; GST stays independently usable.
**pure-translation / enterprise** = a franchise — FEC campaign finance application that consumes SW

## Package Structure

Three layers coexist:

- `swh/` — CLI tool for Census data downloading and PostGIS loading (pre-existing)
- `socialwarehouse/` — Django application with geographic warehouse, star schema, DSTK API, Celery tasks
- `vendor/geodjango_simple_template/` — git submodule (GST), pinned snapshot of [siege-analytics/geodjango_simple_template](https://github.com/siege-analytics/geodjango_simple_template). Provides the `locations` Django app + project-level staticfiles. P1B-B (#68) absorbs GST's `locations` into SW's `INSTALLED_APPS`; URLs mount under `/webapp/` prefix.

## GST integration

`manage.py` adds `vendor/geodjango_simple_template/app/hellodjango/` to `sys.path` so `import locations` resolves. SW's `INSTALLED_APPS` contains `'grappelli'` (admin theme; must precede `'django.contrib.admin'`), `'rest_framework_gis'`, and `'locations'`. SW's `socialwarehouse/urls.py` mounts GST's URL surface under `/webapp/`:

| Path | Source |
|---|---|
| `/webapp/grappelli/` | django-grappelli |
| `/webapp/accounts/` | django.contrib.auth |
| `/webapp/api-auth/` | rest_framework |
| `/webapp/locations/` | GST locations app |

GST's `manage.py` and `hellodjango.settings` are not used by SW. SW's `socialwarehouse.settings.*` is the only settings module. To bump the GST pin: `cd vendor/geodjango_simple_template && git fetch && git checkout <new-sha> && cd ../.. && git add vendor/geodjango_simple_template && git commit`.

```
socialwarehouse/
├── geo/                  # Geographic warehouse app (sw_geo)
│   ├── models/           # Address, AddressBoundaryPeriod, CensusVintageConfig,
│   │                     # Political extensions, Intersections
│   ├── management/       # assign_boundaries, compute_intersections, geocode_addresses
│   ├── serializers/
│   └── tasks.py          # Celery async wrappers
├── warehouse/            # Census star-schema app (sw_warehouse)
│   ├── models/           # DimGeography (SCD2), DimSurvey, DimCensusVariable,
│   │                     # DimTime, DimRedistrictingCycle, FactACSEstimate,
│   │                     # FactDecennialCount, FactUrbanicity, FactElectionResult,
│   │                     # FactPrecinctResult, FactRedistrictingPlan
│   ├── services/         # census_etl, dimension_loader, geographic_enrichment
│   └── management/       # load_warehouse
├── api/                  # DSTK replacement REST API
│   ├── geo/              # 7 endpoints: geocode, reverse_geocode, boundaries, proximity, intersections
│   └── warehouse/        # ViewSets: geographies, election-results, acs-estimates
├── delta/                # Delta Lake + Spark (Phase 4)
├── settings/             # Django settings (base, dev, prod, test)
├── celery_app.py
└── urls.py
```

## Key Models

### Address (sw_geo)
Central record. 60+ fields: address components, geocoding metadata (lat/lon, quality, source), Census unit GEOIDs (state through SLDU), siege_geo ForeignKeys for rich queries. Clean break — siege_geo only, no legacy TIGER FKs.

### AddressBoundaryPeriod (sw_geo)
Temporal boundary snapshots. One row per address per Census vintage. Enables "what CD was this address in during 2016?" across redistricting.

### CensusVintageConfig (sw_geo)
Maps Census decades to effective year ranges. `for_year(2018)` returns 2010 vintage.

### DimGeography (sw_warehouse)
SCD Type 2 geography dimension. Natural key: (geoid, vintage_year). Parent FK for drill-up (tract → county → state).

## Management Commands

```bash
python manage.py geocode_addresses --state TX --source dual
python manage.py assign_boundaries --year 2020 --state TX --populate-fks
python manage.py compute_geographic_intersections --year 2020 --type all
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/geo/geocode/` | GET | Point-in-polygon: lat/lon or address → boundaries |
| `/api/geo/reverse_geocode/` | GET | Coordinates → nearest address |
| `/api/geo/standardize_address/` | GET | Parse address components |
| `/api/geo/boundaries/<type>/` | GET | List boundaries (JSON/GeoJSON) |
| `/api/geo/boundaries/<type>/<geoid>/` | GET | Single boundary with geometry |
| `/api/geo/proximity/` | GET | Boundaries within distance |
| `/api/geo/intersections/` | GET | Pre-computed overlap queries |
| `/api/warehouse/geographies/` | GET | Geography dimension browser |
| `/api/warehouse/election-results/` | GET | Election results by geography |
| `/api/warehouse/acs-estimates/` | GET | ACS demographic estimates |

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run Django
DJANGO_SETTINGS_MODULE=socialwarehouse.settings.development python manage.py runserver

# Run Celery worker
celery -A socialwarehouse.celery_app worker -l info

# Run management commands
python manage.py geocode_addresses --dry-run
```

## Attribution Policy

NEVER include AI or agent attribution in commits, PRs, issues, or any public-facing content.

## Epic Tracking

Reconstitution tracked at [electinfo/enterprise#1306](https://github.com/electinfo/enterprise/issues/1306). Linear label: `epic:sw-dstk`.
