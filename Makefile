
# Variables
DKC ?= docker compose

# Basic operations

down:
	$(DKC) down --remove-orphans

stop:
	$(DKC) stop --remove-orphans

up:
	$(DKC) up -d --remove-orphans

build:
	$(DKC) stop --remove-orphans
	$(DKC) build --remove-orphans
	docker volume create --name=social_warehouse_pg_data

rebuild:
	$(DKC) stop
	$(DKC) build --no-cache
	docker volume create --name=social_warehouse_pg_data

clean:
	$(DKC) down --remove-orphans
	$(DKC) rm --remove-orphans

pg_shell:
	$(DKC) exec postgis psql -U dheerajchand -d gis

python_term:
	$(DKC) exec python /bin/bash

fetch_jars:
	mvn -U org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=org.apache.sedona:sedona-spark-shaded-3.4_2.13:1.5.1
	mvn -U org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=org.datasyslab:geotools-wrapper:1.5.1-28.2
	mvn -U -DremoteRepositories=https://artifacts.unidata.ucar.edu/content/repositories/unidata-releases/ org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=edu.ucar:cdm-core:5.5.3
	cp ~/.m2/repository/org/apache/sedona/sedona-spark-shaded-3.4_2.13/1.5.1/sedona-spark-shaded-3.4_2.13-1.5.1.jar ./jars/
	cp ~/.m2/repository/org/datasyslab/geotools-wrapper/1.5.1-28.2/geotools-wrapper-1.5.1-28.2.jar ./jars/
	cp ~/.m2/repository/edu/ucar/cdm-core/5.5.3/cdm-core-5.5.3.jar ./jars/

