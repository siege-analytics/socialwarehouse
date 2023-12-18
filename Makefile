# Basic operations

down:
	docker-compose down

stop:
	docker compose stop

up:
	docker compose up -d

build:
	docker compose stop
	docker compose build
	docker volume create --name=social_warehouse_pg_data

rebuild:
	docker compose stop
	docker compose build --no-cache
	docker volume create --name=social_warehouse_pg_data

clean:
	docker compose down
	docker compose rm

shell:
	docker compose exec postgis psql -U dheerajchand -d gis

term:
	docker compose exec python /bin/bash

# Functional operations

# 1
ensure-paths:
	docker compose exec python \
		python3 code/python/ensure_paths.py

# 2
fetch-census-shapefiles:
	docker compose exec python \
		python3 code/python/fetch_census_shapefiles.py

#3
fetch-census-acs:
	docker compose exec python \
		python3 code/python/fetch_census_acs.py

# 4
load-voters:
	docker compose exec python \
		python3 code/python/load_voters.py

#5
load-census-shapefiles:
	docker compose exec python \
		python3 code/python/load_census_shapefiles.py

#6
fetch-urbanicity-shapefiles:
	docker compose exec python \
        python3 code/python/fetch_urbanicity_shapefiles.py

#7
load-nces-shapefiles:
	docker compose exec python \
		python3 code/python/load_nces_shapefiles.py

