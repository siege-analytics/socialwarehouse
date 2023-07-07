# Basic operations

down:
	docker-compose down
stop:
	docker compose stop

up: 
  stop
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
	docker compose exec postgis psql

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

hba:
	echo 'Removing md5 auth'
	docker exec -it socialwarehouse-postgis-1 bash -c "sed -i '/host all all all md5/d' /var/lib/postgresql/data/pg_hba.conf"
	echo 'adding password auth'
	docker exec -it socialwarehouse-postgis-1 bash -c "echo 'host all all 0.0.0.0/0 password'>> /var/lib/postgresql/data/pg_hba.conf"
	echo 'final config file'
	docker exec -it socialwarehouse-postgis-1 cat /var/lib/postgresql/data/pg_hba.conf
	echo 'restarting postgres'
	make up

