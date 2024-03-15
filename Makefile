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

pg_shell:
	docker compose exec postgis psql -U dheerajchand -d gis

python_term:
	docker compose exec python /bin/bash



