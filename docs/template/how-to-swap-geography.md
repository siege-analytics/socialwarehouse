# How to swap geography

This guide is for instance projects that need to replace SW's US-Census-based boundary catalog with a different geography (UK Ordnance Survey + ONS Census; EU Eurostat NUTS; Canada Statistics Canada; sub-national systems; custom administrative geographies).

The pattern is documented in [`docs/designs/template-c-boundary-catalog.md`](../designs/template-c-boundary-catalog.md); this guide is the procedural counterpart.

## What a "geography" means in SW

SW's geographic substrate is:

- A **boundary catalog** — the set of polygon/multipolygon types the warehouse keys on (`state`, `county`, `tract`, `block_group`, `block`, `vtd`, `cd`, `sldl`, `sldu`, `zcta`, `place`, `cbsa`, `school_district`, etc. for the US)
- An **Address cache** (`geo.Address`) — denormalized table with one `_geoid` column per boundary type, so address-to-boundary lookups are O(1)
- An **AddressBoundaryPeriod** (`geo.AddressBoundaryPeriod`) — temporal snapshots so historical "which CD was this address in during 2016?" works across redistricting
- A **vintage system** (`CensusVintageConfig`) — maps decades to effective year ranges
- A **Spark+Sedona enrichment library** (`delta/enrichment.py`) — bulk address-to-boundary joins

To swap geography, you replace the *boundary catalog* and the *vintage system* while keeping the *Address cache pattern* and the *enrichment library* intact. The patterns generalize; only the type names and data sources change.

## Step 0 — Pre-author inventory

Before any code change, post a pre-author inventory to the relevant ticket in your instance project's tracker:

```markdown
## Pre-author inventory — geography swap (US Census → <your geography>)

### Inputs read
- SW's current `geo.Address._BOUNDARY_TYPES`
- SW's `geo.AddressBoundaryPeriod` model
- `docs/designs/template-c-boundary-catalog.md`
- `docs/entities/boundary_catalog.md`
- Your geography's authoritative source documentation
  (ONS / Eurostat / StatCan / etc.)

### Knowledge requirements
- What boundary types does your geography offer?
  (List them with the equivalent of GEOID — natural keys)
- What's the vintage/revision cadence?
  (US Census is decennial; UK is decennial but ONS revises mid-decade;
  EU NUTS revises every 3 years; etc.)
- What's the canonical projection/CRS?
  (US Census ships in EPSG:4269; your source may differ)
- Is there a hierarchical containment relationship?
  (US: state ⊃ county ⊃ tract ⊃ block_group ⊃ block; your geography
  may have a different tree or none)
- What's the geocoding source?
  (US: Census TIGER + commercial; UK: OS AddressBase + Royal Mail PAF;
  EU: varies per country)
- Are there electoral boundaries that revise between censuses?
  (US CDs revise per redistricting cycle; UK constituencies revise per
  Boundary Commission review)

### Contact-point measurements
- File a SU ticket (or batched series) for each new boundary type that
  needs a siege_utilities model (per template-c step 1)
- Inventory the SRID of every source dataset before any reproject step
- Measure the row count of the largest source (boundary file for the
  smallest unit — UK Output Areas, Canadian Dissemination Areas, etc.)
  to size the Spark cluster

### Surface areas beyond rules 1-5
- Existing US-specific code in `geo/services/` that needs replacement
  or generalization
- Census-specific management commands (`assign_boundaries`,
  `geocode_addresses --source dual`) that need geography-specific variants
- ACS/QCEW/NCES ingest patterns that are US-specific — see
  per-domain swap (template-d/e/f)

### Hypothesis
"After this swap, `Address._BOUNDARY_TYPES` will contain
`{your_geo_types}`, `AddressBoundaryPeriod` will track temporal
snapshots for `{revisable_types}`, and `assign_boundaries --source
<your-source>` will Spark-join addresses to the new boundaries in
under {target_time} per million addresses."
```

## Step 1 — Inventory your geography's boundary catalog

Produce a table mapping your boundary types to SW's pattern:

| SW US type | Your geography equivalent | Natural key format | Vintage cadence | Source |
|---|---|---|---|---|
| `state` | `country` (UK) / `nuts1` (EU) / `province` (CA) | (your code system) | (cadence) | (source URL) |
| `county` | `ltla` (UK) / `nuts3` (EU) / `census_division` (CA) | ... | ... | ... |
| `tract` | `lsoa` (UK) / `lau` (EU) / `dissemination_area` (CA) | ... | ... | ... |
| ... | ... | ... | ... | ... |

Not every SW type has an equivalent in your geography (US `vtd` has no clean UK analogue). And your geography may have types SW doesn't track (UK output areas; EU LAU2). The mapping is informational — the next step builds your geography's catalog from scratch, not by translating SW's.

## Step 2 — File upstream siege_utilities tickets for new boundary types

For each type in your geography's catalog (regardless of whether it maps to a SW type), file a `siege_utilities` ticket:

```markdown
Title: Add <type> boundary model (instance project: <your-warehouse>)

Scope: vintage-aware boundary model for <type>, sourced from <source>.
Schema: geom (MultiPolygon, EPSG:<srid>), <natural_key>, name,
        <other attributes>, vintage FK.

Pattern: per template-c, see existing siege_utilities boundary
models (e.g. CensusState) as the reference.
```

Some of these may already exist in `siege_utilities` for other instance projects. Grep before filing (per the [check-before-blocking discipline](https://github.com/siege-analytics/siege_utilities)).

## Step 3 — Replace `Address._BOUNDARY_TYPES`

In your instance project's `<your-warehouse>/geo/models/address.py`:

```python
class Address(models.Model):
    # ...

    # Your geography's boundary catalog (replace SW's _BOUNDARY_TYPES)
    _BOUNDARY_TYPES = (
        "country",
        "ltla",
        "msoa",
        "lsoa",
        "output_area",
        "constituency",
        "ward",
        # ...
    )

    # Replace SW's _geoid columns with your natural-key columns.
    # Match the natural-key format from Step 1's table.
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    ltla_code = models.CharField(max_length=9, blank=True, db_index=True)
    msoa_code = models.CharField(max_length=9, blank=True, db_index=True)
    # ...
```

The `_BOUNDARY_TYPES` tuple drives the F11 helpers (`boundary_history(type=...)`, `boundary_on(type, date)`) — they iterate over the tuple, so the helpers automatically cover your new types.

The per-type CharField on `Address` is the cache column. Naming convention: `<type>_<key-format>` (e.g. `lsoa_code`, not `lsoa_geoid` — the suffix should match the geography's terminology so domain authors can grep for what they expect).

## Step 4 — Replace `AddressBoundaryPeriod` columns

Same pattern in `<your-warehouse>/geo/models/abp.py`:

```python
class AddressBoundaryPeriod(models.Model):
    address = models.ForeignKey(Address, on_delete=models.CASCADE)
    vintage = models.ForeignKey(CensusVintageConfig, on_delete=models.PROTECT)

    # Your geography's revisable boundaries get columns here
    constituency_code = models.CharField(max_length=9, blank=True)
    ward_code = models.CharField(max_length=9, blank=True)
    # ...
```

Not every boundary type goes in ABP — only the ones that *revise* (US: cd, sldl, sldu, vtd). Stable boundaries (US: state, county, tract) live only on `Address`. Your geography's revisable set differs (UK constituencies revise periodically; LSOAs are revised per census).

## Step 5 — Replace `CensusVintageConfig`

Rename to something geography-neutral or rename to your geography:

```python
class VintageConfig(models.Model):
    """Maps decades / revisions to effective year ranges.

    For UK ONS: 2011 census effective 2011-2022; 2021 census effective 2022-onwards.
    For EU NUTS: NUTS 2010 effective 2008-2012; NUTS 2013 effective 2012-2015; etc.
    """
    code = models.CharField(max_length=20, unique=True)  # e.g. "2021", "NUTS_2013"
    effective_start = models.DateField()
    effective_end = models.DateField(null=True, blank=True)  # null = current
    description = models.TextField(blank=True)

    @classmethod
    def for_year(cls, year):
        # Return the vintage in effect for the given year
        ...
```

The `for_year(year)` API surface stays the same so downstream code (assets, asset graphs, API endpoints) keeps working.

## Step 6 — Replace `delta/enrichment.py` boundary joins

The Spark+Sedona enrichment pattern generalizes; only the table names + join keys change:

```python
def enrich_addresses_with_boundaries(spark, addresses_table, vintage="2021"):
    """Spatial-enrich addresses with UK boundary attributes."""
    addresses = spark.read.table(addresses_table)

    # Replace SW's state/county/cd joins with your boundary set
    countries = spark.read.format("delta").load(
        get_table_path("silver", f"countries_{vintage}")
    )
    ltlas = spark.read.format("delta").load(
        get_table_path("silver", f"ltlas_{vintage}")
    )
    constituencies = spark.read.format("delta").load(
        get_table_path("silver", f"constituencies_{vintage}")
    )

    enriched = addresses
    for boundary_df, key_col in [
        (countries, "country_code"),
        (ltlas, "ltla_code"),
        (constituencies, "constituency_code"),
    ]:
        enriched = enriched.alias("a").join(
            boundary_df.alias("b"),
            on=expr("ST_Intersects(a.geom, b.geom)"),
            how="left",
        ).select("a.*", col(f"b.{key_col}"))

    return enriched
```

## Step 7 — Replace management commands

US-specific commands (`assign_boundaries`, `load_warehouse`) need geography-specific variants. The cleanest path is:

- Keep the command names (`assign_boundaries`, `geocode_addresses`, `seed_demo`)
- Replace the implementation per-geography
- Use a settings flag (`GEOGRAPHY = "uk"`) or a per-geography subpackage (`<your-warehouse>/geo/uk/services/`) to dispatch

Don't try to make commands "universally geography-aware" — the abstraction layer would be too deep. Geography-specific code is fine; the warehouse architecture (Delta → PostGIS → Django) is what generalizes, not every helper.

## Step 8 — Replace API endpoints' assumptions

`api/geo/` has endpoints that assume US-Census semantics (`geocode --source dual` assumes Census Geocoder + commercial; `civic_lookup` returns US-specific district types). Replace per your geography:

```python
# <your-warehouse>/api/geo/views/civic_lookup.py
def civic_lookup(request):
    """Return UK civic memberships for an address."""
    addr = geocode(request.GET["address"], source="osab")  # Ordnance Survey AddressBase
    return JsonResponse({
        "constituency": addr.constituency_code,
        "ward": addr.ward_code,
        "ltla": addr.ltla_code,
        "msoa": addr.msoa_code,
    })
```

## Step 9 — Test end-to-end

```bash
# Run migrations
python manage.py migrate

# Seed a small region (one ltla or constituency)
python manage.py seed_demo --region <your-test-region>

# Hit the API
curl http://localhost:8000/api/geo/civic_lookup?address=10+Downing+Street
# Should return {"constituency": "...", "ward": "...", ...}
```

## What you DON'T replace

- **The medallion architecture** — bronze/silver/gold still applies; only the table contents change
- **`get_spark_session`, `get_table_path`** — unchanged
- **Dagster `WarehouseConfig`, `SparkResource`, `PostGISResource`** — unchanged; instance project sets `SW_CATALOG=<your_catalog>` via env
- **The `delta_table_asset` and `postgis_materialization_asset` factories** — unchanged; your assets use them
- **The pre-author inventory discipline** — applies to your geography work too

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Spatial joins return empty | SRID mismatch | Inventory source SRID, reproject before join |
| Geocoding works but boundary lookup fails | `_BOUNDARY_TYPES` tuple not updated | Update `Address._BOUNDARY_TYPES` + the corresponding `_code` columns |
| Migration fails with FK constraint | `CensusVintageConfig` renamed but referencers not updated | Find every `vintage = models.ForeignKey(...)` and update the target model |
| ABP queries return no temporal history | Forgot to populate ABP — only `Address` columns updated | Run the per-vintage ABP backfill (model on SW's existing pattern) |

## See also

- [README.md](README.md) — template overview
- [`docs/designs/template-c-boundary-catalog.md`](../designs/template-c-boundary-catalog.md) — the boundary-catalog design (US-specific but the pattern generalizes)
- [`docs/entities/boundary_catalog.md`](../entities/boundary_catalog.md) — SW's actual boundary catalog reference
- [how-to-add-a-new-domain.md](how-to-add-a-new-domain.md) — once geography is swapped, add geography-specific domains
- [how-to-upgrade-from-upstream.md](how-to-upgrade-from-upstream.md) — how to absorb SW improvements without losing your geography customizations
