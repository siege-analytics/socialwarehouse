# Self-hosted geocoding (Nominatim)

Replaces the abandoned `siege-analytics/dstk` geocoding fork with a
self-hosted Nominatim instance under the `geocoding` docker-compose
profile. Closes SW#22.

The public Nominatim endpoint (`nominatim.openstreetmap.org`) is rate-
limited and the OSM Foundation's usage policy prohibits anything close
to bulk geocoding. Self-hosting removes the rate limit and the policy
constraint — at the cost of running PostgreSQL + the Nominatim import
yourself.

## Scope and limitations

**This document covers**: bootstrapping a single-state Nominatim
instance (default: Rhode Island), wiring SW's `geocode_addresses`
command to consume it, and scaling to other states via env overrides.

**This document does NOT cover**: full-US OSM imports (12-24 hours of
import time, ~70 GB on-disk after import); Kubernetes deployment
manifests (the original SW#22 body called for cyberpower-specific
manifests; that's a downstream-project concern and is dropped here);
geocoder quality benchmarking against alternatives.

## Why Rhode Island as the default bootstrap state

RI is the smallest US state by area but has the **highest population
density**. The PBF extract is ~200 MB; the import runs in 10-15 minutes
on a modern laptop. The dense address coverage exercises address-
normalization edge cases (multi-unit residential, fine-grained street
networks, irregular block patterns) in ways that larger but sparser
states wouldn't. So the bootstrap demo is small AND representative.

## Prerequisites

- Docker + docker-compose installed.
- A workspace `.env` file in the repo root.
- ~5 GB free disk for the RI default (substantially more for larger states; see "Scaling to other states").

## Bootstrap

### 1. Set the required Nominatim DB password in `.env`

`docker-compose.yml` uses `${NOMINATIM_DB_PASSWORD:?Set NOMINATIM_DB_PASSWORD in .env}`
to fail-fast if unset — same precedent as the existing
`NEO4J_PASSWORD` enforcement. SW#32 lesson:
default-credentials-in-config files land in git on first commit,
so the compose entry must require operator-set values not default
to literals.

```bash
echo "NOMINATIM_DB_PASSWORD=$(openssl rand -base64 24)" >> .env
```

Pick any sufficiently-random value; the internal Postgres port is not
exposed to the host, so this only protects in-container access.

### 2. (Optional) Override the PBF source

Default is Rhode Island. To bootstrap a different state, add to `.env`:

```bash
NOMINATIM_PBF_URL=https://download.geofabrik.de/north-america/us/california-latest.osm.pbf
```

See `docker/nominatim/.env.example` for the per-state PBF URLs and
expected import durations.

### 3. Bring it up + smoke-test (one command)

```bash
make nominatim-bootstrap-demo
```

This runs:

1. `make up-nominatim` — starts the `nominatim` service.
2. Polls `/status.php` every 30s until the import finishes.
3. Runs `make nominatim-geocode-test ADDRESS="Providence, RI"` and prints the JSON response.

Total wall time: ~12-15 minutes for RI; longer for larger states.

### 4. Wire SW to use the self-hosted instance

Add to `.env`:

```bash
NOMINATIM_URL=http://nominatim:8080
NOMINATIM_USER_AGENT=socialwarehouse-self-host
```

(`http://nominatim:8080` is the in-cluster docker-compose service name +
port. From the host network, use `http://localhost:8080` instead.)

Then run the existing `geocode_addresses` command — it picks up the
new URL via Django settings + the `swh.config.NominatimSettings`
fallback:

```bash
python manage.py geocode_addresses --source nominatim-only --dry-run
```

## Scaling to other states

The mediagis/nominatim image imports one PBF on first boot and doesn't
support incremental state-by-state additions. To "load a different
state":

```bash
# 1. Set NOMINATIM_PBF_URL in .env to the target state's Geofabrik URL
echo "NOMINATIM_PBF_URL=https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf" >> .env  # or edit by hand

# 2. Wipe the existing import + re-run
make clean-nominatim
make up-nominatim
```

`clean-nominatim` stops the container and deletes its volumes — the
next `up-nominatim` re-imports from the new PBF.

To run the **full US** at once:

```bash
# In .env:
NOMINATIM_PBF_URL=https://download.geofabrik.de/north-america-latest.osm.pbf

make clean-nominatim
make up-nominatim
# Then come back in 12-24 hours.
```

The full US is ~70 GB on disk after import. Plan volume sizing.

## Makefile targets

| Target | What |
|---|---|
| `make up-nominatim` | Start the service (first boot imports PBF) |
| `make down-nominatim` | Stop the service (volumes preserved) |
| `make clean-nominatim` | Stop AND delete volumes (force re-import) |
| `make nominatim-status` | Health check — HTTP 200 from `/status.php` when ready |
| `make nominatim-logs` | Tail container logs (import progress lives here) |
| `make nominatim-geocode-test ADDRESS="..."` | Run one geocode query |
| `make nominatim-bootstrap-demo` | Up + wait-for-ready + smoke-test (one command) |

## Smoke tests

Health:

```bash
curl http://localhost:8080/status.php?format=json
# {"status":0,"message":"OK","data_updated":"2026-..."}
```

Single geocode:

```bash
curl "http://localhost:8080/search?q=Providence,+RI&format=json&limit=1"
# [{"lat":"41.823...","lon":"-71.413...", ... }]
```

## Integration with SW's existing `geocode_addresses` command

The command (`socialwarehouse/geo/management/commands/geocode_addresses.py`,
shipped under SW#20) does Census batch API first, then Nominatim for
the misses. The Nominatim call routes through Django's
`NOMINATIM_API_BASE_URL` setting, which (since SW#22) is built from
the `NOMINATIM_URL` env var.

To override per-invocation, the command's `--nominatim-url` flag is
also available:

```bash
python manage.py geocode_addresses --source nominatim-only --nominatim-url http://localhost:8080
```

Both routes converge on the same code path; the env var is the default,
the flag is the override.

## Troubleshooting

### `docker compose ... required variable NOMINATIM_DB_PASSWORD is missing a value`

Set it in `.env`:
```bash
echo "NOMINATIM_DB_PASSWORD=$(openssl rand -base64 24)" >> .env
```

Compose validates the `:?` interpolation file-wide at parse time
(same as `NEO4J_PASSWORD`), so any compose command — including
unrelated ones like `docker compose build python-computation` —
will fail if the var is unset. CI sets a placeholder in `.env`
before invoking compose; operators set a real value per the
`openssl rand` recipe above.

### Import has been running for an hour and not done

Check the size of the PBF. RI is ~15 minutes; CA/TX are 4-7 hours;
full US is 12-24 hours. Check `make nominatim-logs` for progress.

### `make nominatim-status` returns connection-refused

The container hasn't finished its initial start sequence yet. Wait
2-3 minutes and retry. If `make nominatim-logs` shows an error, the
import failed — typically: PBF URL unreachable, or disk full, or
insufficient memory (set `NOMINATIM_THREADS` lower in `.env`).

### Self-hosted Nominatim returns no results for an address that works on the public endpoint

Two likely causes:

1. The address is OUTSIDE the loaded state. RI default = Rhode Island
   only; addresses elsewhere return no match. Load a larger PBF or
   the full US.
2. TIGER address import is disabled. Set
   `NOMINATIM_IMPORT_TIGER_ADDRESSES=true` in `.env` and re-import
   for better rural-address coverage.

## Cross-references

- Original ticket: [SW#22](https://github.com/siege-analytics/socialwarehouse/issues/22)
- Companion geocoding work: [SW#20](https://github.com/siege-analytics/socialwarehouse/issues/20) (Census + Nominatim fallback chain)
- Settings: `swh/config.py` (`NominatimSettings`) and `socialwarehouse/settings/base.py` (`NOMINATIM_API_BASE_URL`)
- Compose service: `docker-compose.yml` under the `geocoding` profile
- Image base: [`mediagis/nominatim:5.0`](https://hub.docker.com/r/mediagis/nominatim)
- PBF source: [Geofabrik North America downloads](https://download.geofabrik.de/north-america/us/)
