# How to add a new domain

This guide is for instance projects that need a domain SW doesn't ship — environmental, transit, real-estate, public-health, education-outcomes, anything that's boundary-keyed and warrants its own bronze/silver/gold/PostGIS/API surface.

If you're adding a new *asset* to a domain that already exists, see [`../orchestration/how-to-add-asset-to-existing-domain.md`](../orchestration/how-to-add-asset-to-existing-domain.md) instead. This guide is for adding the domain itself.

## What a "domain" is in SW

A domain in SW is a coherent slice of warehouse content with:

- A **Django app** (`<your-warehouse>/<domain>/`) containing dim/fact models for the PostGIS serving tier
- A **Delta schema set** in `<your-warehouse>/delta/tables.py` for the domain's bronze/silver/gold tables
- An **ingest pattern** for getting source data into bronze (management commands, sensors, or external pipeline)
- A **Dagster asset module** (`<your-warehouse>/orchestration/assets/<domain>.py`) declaring the bronze→silver→gold→PostGIS asset graph
- An **API surface** (`<your-warehouse>/api/<domain>/`) exposing domain-specific endpoints
- **Documentation** (`docs/entities/<domain>_*.md` for entity reference; optional design doc under `docs/designs/`)

SW's existing domains: `geo` (foundational), `civic`, `demographic`, `economic`, `warehouse` (shared dim/fact). Your new domain follows the same shape.

## Pattern reference

SW's design docs for the existing domains are the canonical pattern reference:

| Domain | Design doc | What to mirror |
|---|---|---|
| Demographic (ACS pattern) | [`docs/designs/template-d-demographic-ingest.md`](../designs/template-d-demographic-ingest.md) | Multi-variable ingest, vintage-keyed, fact-table per estimate type |
| Economic (QCEW/BLS pattern) | [`docs/designs/template-e-economic-ingest.md`](../designs/template-e-economic-ingest.md) | Quarterly cadence, NAICS hierarchy, multi-vintage join |
| Civic (NCES/special districts pattern) | [`docs/designs/template-f-civic-ingest.md`](../designs/template-f-civic-ingest.md) | Boundary-key dependency on geo, attribute-rich fact tables |

Pick the closest pattern to your new domain. For environmental → likely economic (vintage cadence, multi-attribute, boundary-keyed). For real-estate → likely demographic (parcel-level, fact-per-estimate). For transit → mixed; you may need to invent the pattern (see "Step 8" below).

## Step 0 — Pre-author inventory

```markdown
## Pre-author inventory — new domain: <domain-name>

### Inputs read
- This guide
- The closest existing domain's design doc + implementation
- Your data source's documentation
- `docs/architecture.md` (warehouse-first principle)

### Knowledge requirements
- What is the canonical source for this domain's data?
  (URL, API, file format, license, refresh cadence)
- What's the boundary key?
  (Does it key on state/county/tract? On a non-Census boundary
  like watershed / school zone / transit district?)
- What's the temporal grain?
  (Annual? Quarterly? Daily? Point-in-time?)
- What's the natural unit row in bronze?
  (One row per address-year? Per facility-month?
  Per parcel? Per route-day?)
- What fact table(s) will the gold tier need?
  (One fact per estimate type, mirroring ACS's pattern? Or one
  wide fact, mirroring NCES's pattern?)
- What dim tables are reused vs new?
  (DimGeography is always reused; DimTime is reused if temporal;
  DimSource may be new for source attribution; DimMetric may be
  new if your domain is metric-heavy)
- What API endpoints does this domain need?
  (Point-lookup? Boundary-aggregate? Trend-over-time?)

### Contact-point measurements (per [rule:authoring-against-state])
- rule 1: source row count (sample at smallest geography)
- rule 2: ingest tooling config (refresh cadence, API rate limits)
- rule 4: plan shape — if asset graph has many unions or wide joins
- rule 5: grep `<your-warehouse>` for any existing references to
  this domain (in case partial work exists)

### Surface areas beyond rules 1-5
- Existing Django apps (don't collide on app_label)
- Existing dim/fact models (reuse DimGeography, DimTime; only
  introduce new dims if your domain genuinely needs them)
- Existing API URL prefixes (don't collide on `/api/<prefix>/`)
- Existing seed_demo command (your domain joins the seed)

### Hypothesis
"After this domain ships, `<your-warehouse>/<domain>/` will contain
{N} dim tables ({list}) and {M} fact tables ({list}), each indexed by
`<boundary>_code` + `vintage`. The asset graph will materialize
{bronze_table} → {silver_table} → {gold_table} → {postgis_target}
on a {cadence} schedule. API endpoints {list} surface the gold tier
to the web app."
```

## Step 1 — Create the Django app

```bash
cd <your-warehouse>
python manage.py startapp <domain>
```

Then in `<your-warehouse>/<domain>/apps.py`:

```python
from django.apps import AppConfig

class <Domain>Config(AppConfig):
    name = "<your-warehouse>.<domain>"
    label = "<prefix>_<domain>"  # e.g. "uk_health", "ca_transit"
    verbose_name = "<Human-readable name>"
```

Register in `<your-warehouse>/settings/base.py`:

```python
INSTALLED_APPS = [
    # ...
    "<your-warehouse>.<domain>",
]
```

## Step 2 — Declare the bronze/silver/gold Delta schemas

In `<your-warehouse>/delta/tables.py`, add your domain's table set:

```python
# ── <Domain> bronze ─────────────────────────────────────────

<DOMAIN>_BRONZE_<TABLE>_SCHEMA = StructType([
    StructField("source_id", StringType(), nullable=False),
    StructField("attribute_a", StringType(), nullable=True),
    StructField("attribute_b", DoubleType(), nullable=True),
    # ... raw source columns as StringType where unsure ...
    StructField("ingested_at", TimestampType(), nullable=False),
])

# ── <Domain> silver ─────────────────────────────────────────

<DOMAIN>_SILVER_<TABLE>_SCHEMA = StructType([
    StructField("<boundary>_code", StringType(), nullable=False),  # boundary key
    StructField("vintage", StringType(), nullable=False),
    StructField("attribute_a_typed", StringType(), nullable=False),
    StructField("attribute_b_typed", DecimalType(18, 4), nullable=True),
    # ... canonical typed columns ...
])

# ── <Domain> gold ───────────────────────────────────────────

<DOMAIN>_GOLD_<TABLE>_SCHEMA = StructType([
    # Enriched columns; boundary attributes joined in; ready for PostGIS load
    ...
])
```

Register in `TABLES = {...}`:

```python
TABLES = {
    # ...
    "<domain>/bronze/<table>": <DOMAIN>_BRONZE_<TABLE>_SCHEMA,
    "<domain>/silver/<table>": <DOMAIN>_SILVER_<TABLE>_SCHEMA,
    "<domain>/gold/<table>": <DOMAIN>_GOLD_<TABLE>_SCHEMA,
}
```

## Step 3 — Declare the PostGIS dim/fact models

In `<your-warehouse>/<domain>/models/`:

```python
# <your-warehouse>/<domain>/models/dimensions.py
class Dim<Domain>Source(models.Model):
    """Source attribution for <domain> facts."""
    name = models.CharField(max_length=100, unique=True)
    url = models.URLField()
    license = models.CharField(max_length=100)
    # ...

    class Meta:
        app_label = "<prefix>_<domain>"


# <your-warehouse>/<domain>/models/facts.py
class Fact<Domain>Measurement(models.Model):
    geography = models.ForeignKey(
        "warehouse.DimGeography",
        on_delete=models.PROTECT,
        related_name="<domain>_measurements",
    )
    time = models.ForeignKey(
        "warehouse.DimTime",
        on_delete=models.PROTECT,
    )
    source = models.ForeignKey(Dim<Domain>Source, on_delete=models.PROTECT)
    metric_value = models.DecimalField(max_digits=18, decimal_places=4)
    # ...

    class Meta:
        app_label = "<prefix>_<domain>"
        indexes = [
            models.Index(fields=["geography", "time"]),
            models.Index(fields=["source"]),
        ]
```

Reuse `DimGeography`, `DimTime` from `warehouse/`; introduce new dims only if your domain genuinely needs them (DimSource if source attribution matters; DimMetric if metric-heavy).

Generate the migration:

```bash
python manage.py makemigrations <domain>
```

## Step 4 — Write the ingest pattern

Three shapes; pick one:

### Shape A — Management command (one-shot or periodic)

```python
# <your-warehouse>/<domain>/management/commands/load_<source>.py
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--vintage", required=True)
        parser.add_argument("--state", default=None)

    def handle(self, *args, **options):
        # Fetch source data; write to bronze Delta path
        ...
```

Best for: sources with a fixed-cadence batch refresh (annual surveys, quarterly releases).

### Shape B — Dagster sensor + asset (event-driven)

```python
# <your-warehouse>/orchestration/sensors.py
@sensor(job=<domain>_refresh_job)
def <source>_arrival_sensor(context):
    # Detect new data at the source (S3 prefix, RSS feed, etc.)
    # Request materialization when new
    ...
```

Best for: sources that arrive irregularly (real-time API, vendor file drops).

### Shape C — External pipeline writes bronze; Dagster picks up

The source data lands in bronze via a pipeline outside SW (Airbyte, custom ingest service). SW's bronze is declared as a `SourceAsset` and the silver/gold assets pick up automatically.

Best for: sources owned by a separate team or system.

## Step 5 — Write the Dagster asset module

Mirror the geo module pattern. See [`../orchestration/how-to-add-asset-to-existing-domain.md`](../orchestration/how-to-add-asset-to-existing-domain.md) for the detailed asset-authoring workflow. The brief version:

```python
# <your-warehouse>/orchestration/assets/<domain>.py
from dagster import AssetKey, SourceAsset
from socialwarehouse.orchestration.asset_factories import (
    delta_table_asset,
    postgis_materialization_asset,
)

<table>_raw = SourceAsset(
    key=AssetKey(["warehouse", "bronze", "<domain>_<table>"]),
    description="Raw <domain> ingest from <source>.",
    group_name="bronze",
)

def _compute_<table>_typed(context, spark):
    # Bronze → silver typing transform
    ...

<table>_typed = delta_table_asset(
    layer="silver",
    table="<domain>_<table>_typed",
    deps=["bronze/<domain>_<table>"],
    compute_fn=_compute_<table>_typed,
)

# ... gold asset, PostGIS materialization asset ...

all_assets = [<table>_raw, <table>_typed, ...]
```

Register in `<your-warehouse>/orchestration/assets/__init__.py` and update `definitions.py` to include the new domain.

## Step 6 — Write the API surface

```python
# <your-warehouse>/api/<domain>/urls.py
urlpatterns = [
    path("lookup/", <Domain>LookupView.as_view(), name="<domain>-lookup"),
    path("aggregate/", <Domain>AggregateView.as_view(), name="<domain>-aggregate"),
]

# <your-warehouse>/api/urls.py — mount the new sub-router
urlpatterns = [
    # ...
    path("<domain>/", include("<your-warehouse>.api.<domain>.urls")),
]
```

The endpoint pattern follows DRF + the existing SW `geo` API conventions. See `<your-warehouse>/api/geo/` for the canonical shape.

## Step 7 — Add to seed_demo

```python
# <your-warehouse>/<domain>/management/commands/_seed_demo_<domain>.py
def seed_<domain>(state, vintage):
    """Tiny seed for <domain> — one state, one vintage."""
    ...

# <your-warehouse>/management/commands/seed_demo.py
class Command(BaseCommand):
    def handle(self, *args, **options):
        # ... existing seed calls ...
        seed_<domain>(options["state"], options["vintage"])
```

The seed should load **one state, one vintage, small variable subset** — fast (under a minute) so the quickstart stays under an hour.

## Step 8 — When your domain doesn't fit the existing patterns

If your domain has shape that none of D/E/F covers (e.g. event-stream-shaped like transit, or hierarchical-tree-shaped like classifications):

1. Write a design doc at `<your-instance>/docs/designs/<domain>.md` explaining the shape and the pattern you're inventing
2. File it as an issue in your instance project
3. Implement; revisit the doc after the first end-to-end works
4. If the pattern is generally useful, consider upstreaming as a new SW template-readiness track

Don't try to force a shape-fit if the existing patterns are wrong for your domain — that's how warehouse-first discipline breaks down.

## Documentation

For every new domain:

- **One entity doc per dim/fact**: `<your-instance>/docs/entities/<domain>_<entity>.md` describing the table, columns, business meaning, source provenance
- **Optional design doc**: `<your-instance>/docs/designs/<domain>-ingest.md` if the pattern is non-obvious (mirrors template-d/e/f)
- **Update CLAUDE.md** if you have one: package structure section gets the new app

## See also

- [README.md](README.md) — template overview
- [how-to-fork-and-rename.md](how-to-fork-and-rename.md) — prerequisite for adding domains in your instance
- [how-to-swap-geography.md](how-to-swap-geography.md) — if your domain keys on non-US boundaries
- [`../orchestration/how-to-add-asset-to-existing-domain.md`](../orchestration/how-to-add-asset-to-existing-domain.md) — asset-level workflow inside the new domain module
- [`docs/architecture.md`](../architecture.md) — the warehouse-first principle (your new domain must respect it)
- [`docs/designs/template-{d,e,f}-*.md`](../designs/) — the existing-domain patterns to copy
