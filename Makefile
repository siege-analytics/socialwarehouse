# Basic operations

down:
	docker-compose down --remove-orphans

stop:
	docker compose stop --remove-orphans

up:
	docker compose up -d --remove-orphans

build:
	docker compose stop --remove-orphans
	docker compose build --remove-orphans
	docker volume create --name=social_warehouse_pg_data

rebuild:
	docker compose stop
	docker compose build --no-cache
	docker volume create --name=social_warehouse_pg_data

clean:
	docker compose down --remove-orphans
	docker compose rm --remove-orphans

pg_shell:
	docker compose exec postgis psql -U dheerajchand -d gis

python_term:
	docker compose exec python /bin/bash



