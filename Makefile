
# # #
# Configure Run Environment
#

# export DKC=docker-compose for docker-compose v1
DKC ?= docker compose

# modest performance improvement since we aren't compiling C code
MAKEFLAGS += --no-builtin-rules 
.SUFFIXES: # cancel suffix rules

# # #
# Jobs

pg_shell:
	$(DKC) exec postgis psql -U dheerajchand -d gis

python_term:
	$(DKC) exec python /bin/bash

# # #
# Docker Compose Profiles
#

# # #
# include YAML files docker/*.yml
# *.profile.* files sorted first
define compose-profile-includes
$(strip \
	$(shell find docker -type f -name '*.profile.*' | sort) \
	$(shell find docker -type f -name '*.yml' | sort) \
)
endef

# default to all profiles
COMPOSE_FILES ?= ${compose-profile-includes}

ifdef DEBUG
$(info COMPOSE_FILES=${COMPOSE_FILES})
endif

docker-compose.yml: .env ${COMPOSE_FILES}
ifndef COMPOSE_FILES
	$(error COMPOSE_FILES is not set)
endif
	$(DKC) $(foreach f,$(filter-out .env,$^),-f $f) config > $@ $(if ${DEBUG},,2>/dev/null)


# # #
# include ENV files conf/*.env
define compose-env-includes
$(strip \
	$(shell find conf -type f -name '*.env' | sort) \
)
endef

# default to all env files
COMPOSE_ENV_FILES ?= ${compose-env-includes}

ifdef DEBUG
$(info COMPOSE_ENV_FILES=${COMPOSE_ENV_FILES})
endif

.env: ${COMPOSE_ENV_FILES}
ifndef COMPOSE_ENV_FILES
	$(error COMPOSE_ENV_FILES is not set)
endif
	@cat $^ >$@

# # #
# Docker Compose Service Commands

up: .env docker-compose.yml
	$(DKC) up -d

down: .env docker-compose.yml
	$(DKC) down --remove-orphans

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

# # #
# Setup
#

# probably too aggressive
clean_jars:
	rm -rf ./jars
	mkdir ./jars

fetch_jars:
	$(DKC) down
	$(DKC) up -d --scale maven=3  maven # Scale up the Maven service - add more if desired
	#
	$(DKC) exec -T --index 1 maven mvn -U org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=org.apache.sedona:sedona-spark-shaded-3.4_2.13:1.5.1 && \
	$(DKC) exec -T --index 1 maven cp /root/.m2/repository/org/apache/sedona/sedona-spark-shaded-3.4_2.13/1.5.1/sedona-spark-shaded-3.4_2.13-1.5.1.jar ./jars/
	#
	$(DKC) exec -T --index 2 maven mvn -U org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=org.datasyslab:geotools-wrapper:1.5.1-28.2 && \
	$(DKC) exec -T --index 2 maven cp /root/.m2/repository/org/datasyslab/geotools-wrapper/1.5.1-28.2/geotools-wrapper-1.5.1-28.2.jar ./jars/
	#
	$(DKC) exec -T --index 3 maven mvn -U -DremoteRepositories=https://artifacts.unidata.ucar.edu/content/repositories/unidata-releases/ org.apache.maven.plugins:maven-dependency-plugin:3.1.2:get -Dartifact=edu.ucar:cdm-core:5.5.3 && \
	$(DKC) exec -T --index 3 maven cp /root/.m2/repository/edu/ucar/cdm-core/5.5.3/cdm-core-5.5.3.jar ./jars/
	$(DKC) down  # Bring down the services after completion


