# Social Warehouse — Makefile
# https://github.com/siege-analytics/socialwarehouse
#
# Targets are grouped: services, shells, spark, setup.
# Run `make help` to list them all.

DKC ?= docker compose

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

.PHONY: up down build rebuild clean prune help

up:  ## Start PostGIS + Python (default profile)
	$(DKC) up -d

up-spark:  ## Start with Spark cluster
	$(DKC) --profile spark up -d

up-full:  ## Start everything (Spark + Zeppelin + Maven)
	$(DKC) --profile full up -d

down:  ## Stop all services
	$(DKC) down --remove-orphans

build:  ## Build images
	$(DKC) build

build-spark:  ## Build images including Spark
	$(DKC) --profile spark build

rebuild:  ## Rebuild images from scratch (no cache)
	$(DKC) build --no-cache

clean:  ## Stop services and remove volumes
	$(DKC) down --remove-orphans -v

prune:  ## Remove stopped containers system-wide
	docker container prune -f

# ---------------------------------------------------------------------------
# Shells
# ---------------------------------------------------------------------------

.PHONY: pg-shell python-shell spark-shell

pg-shell:  ## Open a psql shell
	$(DKC) exec postgis psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

python-shell:  ## Open a bash shell in the Python container
	$(DKC) exec python-computation /bin/bash

spark-shell:  ## Open spark-shell on the master
	$(DKC) exec spark-master spark-shell

# ---------------------------------------------------------------------------
# Spark / Sedona JARs
# ---------------------------------------------------------------------------

SEDONA_VERSION  ?= 1.5.1
GEOTOOLS_VERSION ?= 1.5.1-28.2

.PHONY: fetch-jars clean-jars

fetch-jars:  ## Download Sedona + GeoTools JARs via Maven
	$(DKC) --profile full up -d maven
	$(DKC) exec maven mvn -U \
		org.apache.maven.plugins:maven-dependency-plugin:3.6.1:get \
		-Dartifact=org.apache.sedona:sedona-spark-shaded-3.4_2.13:$(SEDONA_VERSION)
	$(DKC) exec maven cp \
		/root/.m2/repository/org/apache/sedona/sedona-spark-shaded-3.4_2.13/$(SEDONA_VERSION)/sedona-spark-shaded-3.4_2.13-$(SEDONA_VERSION).jar \
		./jars/
	$(DKC) exec maven mvn -U \
		org.apache.maven.plugins:maven-dependency-plugin:3.6.1:get \
		-Dartifact=org.datasyslab:geotools-wrapper:$(GEOTOOLS_VERSION)
	$(DKC) exec maven cp \
		/root/.m2/repository/org/datasyslab/geotools-wrapper/$(GEOTOOLS_VERSION)/geotools-wrapper-$(GEOTOOLS_VERSION).jar \
		./jars/
	$(DKC) stop maven

clean-jars:  ## Remove downloaded JARs
	rm -rf ./jars/*.jar

# ---------------------------------------------------------------------------
# Census data (via siege_utilities inside the Python container)
# ---------------------------------------------------------------------------

.PHONY: download-census load-census

download-census:  ## Download Census TIGER shapefiles
	$(DKC) exec python-computation python -m swh.cli download-census

load-census:  ## Load Census shapefiles into PostGIS
	$(DKC) exec python-computation python -m swh.cli load-census

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
