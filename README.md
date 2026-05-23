# The Social Warehouse

A multi-domain data warehouse and data lake system for social, civic, demographic, and economic analysis from [Siege Analytics](1). The US-default configuration ships with geography, civic, demographic, and economic domains keyed to US Census boundaries — but **the architecture is a template**, not a finished product, and the value comes from forking it for your own geography or domain combination.

## Use this as a template

SocialWarehouse is designed to be forked. The same architecture (Delta Lake medallion → PostGIS star-schema → Django ORM, with Dagster orchestration on top) works for any boundary-keyed multi-domain warehouse. Instance projects fork SW, rename the package, swap the geography (US → UK, EU, regional), and add or replace domains, inheriting orchestration + factories + resource patterns from upstream.

**Are you here because…**

| You want to | Read first |
|---|---|
| **Fork SW for your own warehouse** (UK, EU, regional, topic-specific) | [`docs/quickstart.md`](docs/quickstart.md) then [`docs/orchestration/instance-project-guide.md`](docs/orchestration/instance-project-guide.md) |
| **Run SW locally to see what it does** | [`docs/quickstart.md`](docs/quickstart.md) — `git clone` to seeded dev instance in under an hour |
| **Add a new asset to an existing SW domain** (e.g. a new silver transformation) | [`docs/orchestration/how-to-add-asset-to-existing-domain.md`](docs/orchestration/how-to-add-asset-to-existing-domain.md) |
| **Operate Dagster** (local dev, debug failures, deploy to prod) | [`docs/orchestration/how-to-operate.md`](docs/orchestration/how-to-operate.md) |
| **Look up env vars, asset key conventions, factory signatures** | [`docs/orchestration/reference.md`](docs/orchestration/reference.md) |
| **Understand the warehouse-first architecture** | [`docs/architecture.md`](docs/architecture.md) |
| **Understand the template-readiness design decisions** (vintage polymorphization, boundary catalog, ingest patterns, init flow) | [`docs/designs/template-{b,c,d,e,f,g}-*.md`](docs/designs/) |

### What you get out of the box

- **Delta Lake layer** (`socialwarehouse/delta/`) — bronze/silver/gold medallion with reusable Spark + Sedona configuration, table-path helpers, and a Spark-based geographic enrichment library
- **PostGIS serving tier** with a star-schema dimensional model (`DimGeography` SCD2, `FactACSEstimate`, `FactDecennialCount`, `FactElectionResult`, `FactPrecinctResult`, `FactRedistrictingPlan`)
- **Dagster orchestration** (optional extra `[orchestration]`) — `ConfigurableResource`s, asset factories, demo `geo` asset graph end-to-end (bronze → silver → gold → PostGIS), one schedule + sensor example
- **Django REST API** (DSTK replacement) — geocoding, reverse-geocoding, boundary lookup, proximity, intersections, civic-lookup
- **Django web app frame** via [`geodjango_simple_template`](https://github.com/siege-analytics/geodjango_simple_template) git submodule

### What you bring

- Your own geography ingests (US Census ships in the box; other geographies fork the ingest pattern from `docs/designs/template-c-boundary-catalog.md`)
- Your own domain-specific asset graphs (geo demo ships; civic, demographic, economic land via [SW#277-279](https://github.com/siege-analytics/socialwarehouse/issues/277))
- Instance-specific Django settings (the package supports a settings hierarchy; instance projects override `socialwarehouse.settings.prod`)

Built with:

- [Kubernetes](4)
- [MinIO](13)

Runs:

- [PostgreSQL](5) + [PostGIS](6)
- [Python](7)
- [R](8) (NOT YET)
- [Geoserver](9) (NOT YET)
- [Zeppelin Notebook](10)
- [GeoTrellis](11) (NOT YET)
- [Ubuntu](12)
- [dbt](14)
- [Spark](15) (FIXING)

Data warehouse is built to enable longitudinal analysis from [Census](2) and [Bureau of Labour Statistics](3).
Intended growth:
- FEC information
- Election results
- Media markets
- Officials and jurisdictions

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for project-level architectural principles. The foundational rule: **warehouse first, web app last** — Delta Lake schemas are canonical; PostGIS star-schema dimensional models are the serving tier; the Django web app is a downstream read-only consumer.

## Cloning

This repo uses a git submodule for the GeoDjango template (GST) at `vendor/geodjango_simple_template/`. Clone with submodules:

```bash
git clone --recurse-submodules git@github.com:siege-analytics/socialwarehouse.git
```

If you already have a clone without submodules:

```bash
git submodule update --init --recursive
```

The GST submodule is a pinned snapshot of [siege-analytics/geodjango_simple_template](https://github.com/siege-analytics/geodjango_simple_template). To bump the pin: `cd vendor/geodjango_simple_template && git fetch && git checkout <new-sha> && cd ../.. && git add vendor/geodjango_simple_template && git commit`.

## Using

It's recommended to use `make` to run the `docker compose` commands below because we are auto-generating `docker-compose.yml` and `.env` files. Because of the magic of `make`, changes to the source includes will automatically trigger a re-make of the compose files.*See below for more on how to work with the auto-generation*.

As always, `compose.override.yml` can be used if you need changes to the auto-generated configs.

**Here are the `make` commands that wrap docker compose:**
- `down` - this will terminate the containers, volumes, networks and remove them. It's a last resort command.
- `up` - this will start containers, networks, volumes from rest and run them in detached mode.
- `build` - this will build the containers, networks and volumes.
- `rebuild` - this will build the containers, networks, volumes from nothing, not relying on cached resources. [`docker compose build --no-cache`]
- `clean` - this will terminate the containers, volumes and networks, and remove them.
- `prune` - this will remove all stopped containers, without removing running containers.

**Here are some of the important `make` commands for working with the containers:**
- `pg_shell` - this will create an `ssh` connection to the `PostgreSQL` server container.
- `python_term` - this will create an `ssh` connection to the `Python` container
- `fetch_jars` - this uses `maven` to get `jar` files that are used by `Spark` to operate. It will save them in the default location copy them to the `jars` directory in the project.

## Auto-generated Compose Files

By default, all `.yml` files in the `docker/` directory are used to generate the `docker-compose.yml` file. The `.env` file is generated from `.env` files in the `conf/` directory.

All of the wrapped compose commands declare `.env` and `docker-compose.yml` as dependencies, so they will be re-generated if any of the `.yml` files or `.env` files change.

Note, that a service may be defined across multiple files, and the order of the files is important. The `docker-compose.yml` file is generated by concatenating the files in the order they are listed in the `COMPOSE_FILES` variable. The auto-generated file-list sorts `.profile.yml` files to the end of the list, so that they have precedence over the plain `.yml` files.

You can explicitly select the include files by using the `COMPOSE_FILES` and `COMPOSE_ENV_FILES` variables when you run `make`. You might add such overrides to new targets in the Makefile, so you can define custom stacks for different environments or purposes.

```Makefile
mycustom:
	# use -B to force a rebuild of docker-compose.yml
	$(MAKE) -B COMPOSE_FILES="docker/mycustom.yml docker/mycustom.profile.yml" up
```

If you don't want your additional configs auto-included in default runs, just use a different naming convention.

## Adding Services

To compile the compose file snipits from the `docker/` sub-directory, we set the `--project-directory` to the repo root. Beware then defining any paths in the compose snipits, that the current working directory is the repo root. Whereas, remember that the Dockerfile paths are relative to the build-context you set.

It is recommended that you create a generalized `.yml` file for each image you build. Then put additional configurations into a `.profile.yml` file. The `.profile.yml` files will always have precedence over service descriptions in plain `.yml` files. You might group related services into a profile, or add project-specific or environment-specific configurations, such as volumes, networks, or environment variables.

For instance, we define image-building configurations in `docker/spark-build-image.yml` and define our integration of the image into the various services in `docker/spark.profile.yml`. You can see how we use one image in multiple services with different envrionment variables and volumes.

## Dagster orchestration

Warehouse pipeline orchestration lives in `socialwarehouse/orchestration/`
and is an **optional extra** (`pip install -e ".[orchestration]"`).
The full guide — install, local dev, debugging, production deployment,
adding assets, instance-project extension — lives at
[`docs/orchestration/`](docs/orchestration/README.md).

Quick start:

```bash
pip install -e ".[orchestration]"
export DJANGO_SETTINGS_MODULE=socialwarehouse.settings.dev
export SW_WAREHOUSE_ROOT=file:///tmp/sw-warehouse
dagster dev -m socialwarehouse.orchestration
```

Open http://localhost:3000 for the asset graph (bronze → silver → gold → PostGIS).
Dagster is **separate from Celery** — Dagster orchestrates the warehouse
pipeline; Celery handles web-app-triggered async tasks.

## References

- [How to make sdkman run in Dockerfile](16)
- [GDAL Fix for Ubuntu](17)
- [JAVA_HOME Variable for sdkman in Dockerfile](18)
- [Adding sdkman into Dockerfile](19)
- [Running a Python Venv in Dockerfile](20)

[1]: http://www.siegeanalytics.com
[2]: http://www.census.gov
[3]: http://www.bls.gov
[4]: https://kubernetes.io
[5]: https://www.postgresql.org
[6]: https://www.postgis.net
[7]: https://www.python.org
[8]: https://www.r-project.org
[9]: https://www.geoserver.org
[10]: https://zeppelin.apache.org
[11]: https://geotrellis.readthedocs.io/en/latest/
[12]: https://www.ubuntu.org
[13]: https://www.min.io
[14]: https://medium.com/israeli-tech-radar/first-steps-with-dbt-over-postgres-db-f6b350bf4526
[15]: https://medium.com/@MarinAgli1/setting-up-a-spark-standalone-cluster-on-docker-in-layman-terms-8cbdc9fdd14b
[16]: https://stackoverflow.com/questions/62188599/cannot-build-dockerfile-with-sdkman
[17]: https://gis.stackexchange.com/questions/28966/python-gdal-package-missing-header-file-when-installing-via-pip
[18]: https://github.com/sdkman/sdkman-cli/issues/431
[19]: https://stackoverflow.com/questions/53656537/install-sdkman-in-docker-image
[20]: https://pythonspeed.com/articles/activate-virtualenv-dockerfile/