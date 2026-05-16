#!/usr/bin/env zsh
# =================================================================
# SW DEV ENVIRONMENT
# =================================================================
# Source this file from within the socialwarehouse repo root:
#
#   source ./dev/sw.zsh
#
# Requires siege_analytics_zshrc installed:
#   https://github.com/dheerajchand/siege_analytics_zshrc
#
# One-time setup:
#   git clone https://github.com/dheerajchand/siege_analytics_zshrc
#   cd siege_analytics_zshrc && bash install.sh
# =================================================================

# -----------------------------------------------------------------
# GST submodule init check
# -----------------------------------------------------------------
# vendor/geodjango_simple_template/ is a git submodule. If the clone
# was done without --recurse-submodules, the directory exists but is
# empty -- warn the operator instead of letting Django imports silently
# resolve to nothing later.
if [[ -d "vendor/geodjango_simple_template" && ! -e "vendor/geodjango_simple_template/app" ]]; then
    echo "⚠️  GST submodule not initialised. Run:"
    echo "      git submodule update --init --recursive"
    echo "   See README.md \"Cloning\" for details."
fi

# -----------------------------------------------------------------
# Load framework modules
# -----------------------------------------------------------------
_SW_MODULES="${ZSHRC_CONFIG_DIR:-$HOME/.config/zsh}/modules"

if [[ ! -d "$_SW_MODULES" ]]; then
    echo "⚠️  siege_analytics_zshrc not installed — falling back to minimal mode"
    echo "   https://github.com/dheerajchand/siege_analytics_zshrc"
    _SW_FRAMEWORK_AVAILABLE=0
else
    _SW_FRAMEWORK_AVAILABLE=1
    for _mod in docker database doctor; do
        if ! typeset -f "${_mod}_status" >/dev/null 2>&1; then
            source "$_SW_MODULES/${_mod}.zsh" 2>/dev/null || true
        fi
    done
    unset _mod
fi
unset _SW_MODULES

# -----------------------------------------------------------------
# Load .env into shell (safe: only known vars)
# -----------------------------------------------------------------
if [[ -f ".env" ]]; then
    while IFS='=' read -r key val; do
        [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
        val="${val%%#*}"          # strip inline comments
        val="${val%"${val##*[! ]}"}"  # rtrim
        export "$key"="$val"
    done < .env
fi

# Wire PostGIS vars from .env values so database.zsh functions work
export PGHOST="${POSTGRES_HOST:-localhost}"
export PGPORT="${POSTGRES_PORT:-5432}"
export PGDATABASE="${POSTGRES_DB:-}"
export PGUSER="${POSTGRES_USER:-postgres}"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"

# Override Sedona version to match this repo
export SPARK_SEDONA_VERSION="1.9.0"
export SPARK_GEOTOOLS_VERSION="1.9.0-33.1"

# -----------------------------------------------------------------
# SW-specific helpers
# -----------------------------------------------------------------

# Full stack status: containers + PostGIS + Neo4j
sw_status() {
    echo "================================================================"
    echo " socialwarehouse stack"
    echo "================================================================"

    if (( _SW_FRAMEWORK_AVAILABLE )); then
        docker_status
    else
        docker compose ps
    fi

    echo ""
    echo "● PostGIS"
    if (( _SW_FRAMEWORK_AVAILABLE )); then
        pg_test_connection
    else
        docker compose exec postgis pg_isready -U "${PGUSER}" 2>/dev/null \
            && echo "  ✅ PostGIS reachable" || echo "  ❌ PostGIS not reachable"
    fi

    echo ""
    echo "● Neo4j"
    if docker compose exec neo4j cypher-shell \
            -u neo4j -p "${NEO4J_PASSWORD:-}" \
            "RETURN 1" >/dev/null 2>&1; then
        echo "  ✅ Neo4j reachable"
    else
        echo "  ❌ Neo4j not reachable (not started, or wrong password)"
    fi
}

# Build images
sw_build() {
    echo "🏗️  Building SW images..."
    docker compose build "$@"
}

# Start core services (PostGIS, Redis, Django, Celery, Neo4j)
sw_up() {
    echo "🚀 Starting SW core services..."
    docker compose up -d "$@"
}

# Start with Spark profile
sw_up_spark() {
    echo "🚀 Starting SW + Spark..."
    docker compose --profile spark up -d "$@"
}

# Run the Django test suite
sw_test() {
    echo "🧪 Running SW test suite..."
    docker compose run --rm python-computation python -m pytest tests/ -v "$@"
}

# Run a single test file or pattern
sw_test_one() {
    local target="${1:?Usage: sw_test_one tests/unit/geo/test_models.py}"
    echo "🧪 Running: $target"
    docker compose run --rm python-computation python -m pytest "$target" -v "${@:2}"
}

# Interactive shell in python-computation
sw_shell() {
    docker compose run --rm python-computation bash
}

# psql session into PostGIS
sw_db() {
    docker compose exec postgis psql -U "${PGUSER}" -d "${PGDATABASE}"
}

# Tail logs (all services, or pass service names)
sw_logs() {
    docker compose logs -f "$@"
}

# Django management command shorthand
# Usage: sw_manage migrate
#        sw_manage check
#        sw_manage shell
sw_manage() {
    docker compose run --rm python-computation python manage.py "$@"
}

# Run migrations
sw_migrate() {
    sw_manage migrate "$@"
}

# Full teardown (removes volumes)
sw_down() {
    echo "🛑 Stopping SW stack and removing volumes..."
    docker compose --profile spark down -v "$@"
}

# Clean Docker resources between test runs
sw_clean() {
    echo "🧹 Cleaning Docker resources..."
    if (( _SW_FRAMEWORK_AVAILABLE )); then
        docker_cleanup
    else
        docker system prune -f
    fi
}

# Pre-flight check
sw_doctor() {
    echo "================================================================"
    echo " sw_doctor — pre-flight check"
    echo "================================================================"
    echo ""

    if (( _SW_FRAMEWORK_AVAILABLE )); then
        zsh_doctor
        echo ""
    fi

    echo "● SW environment"

    # Docker daemon
    if docker info >/dev/null 2>&1; then
        echo "  ok    Docker daemon running"
    else
        echo "  FAIL  Docker not running — open Docker Desktop"
        return 1
    fi

    # Minimum Docker memory (warn if < 5 GB)
    local mem_bytes
    mem_bytes=$(docker system info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
    if (( mem_bytes > 0 && mem_bytes < 5368709120 )); then
        local mem_gb=$(( mem_bytes / 1073741824 ))
        echo "  warn  Docker memory: ${mem_gb} GB — recommend 6 GB+ (Docker Desktop → Resources)"
    elif (( mem_bytes >= 5368709120 )); then
        echo "  ok    Docker memory: $(( mem_bytes / 1073741824 )) GB"
    fi

    # .env file
    if [[ -f ".env" ]]; then
        echo "  ok    .env present"
    else
        echo "  warn  .env missing — cp .env.example .env and fill in passwords"
    fi

    # Required env vars
    for var in POSTGRES_PASSWORD NEO4J_PASSWORD DJANGO_SECRET_KEY; do
        local val="${(P)var}"
        if [[ -n "$val" ]]; then
            echo "  ok    $var is set"
        else
            echo "  warn  $var not set (check .env)"
        fi
    done

    # NEO4J_PASSWORD length
    if [[ -n "${NEO4J_PASSWORD}" && ${#NEO4J_PASSWORD} -lt 8 ]]; then
        echo "  FAIL  NEO4J_PASSWORD is shorter than 8 chars — Neo4j will refuse to start"
    fi

    # Disk space (warn < 8 GB free)
    local free_kb
    free_kb=$(df -k . | awk 'NR==2 {print $4}')
    if (( free_kb < 8388608 )); then
        echo "  warn  < 8 GB free disk — build may fail"
    else
        echo "  ok    disk space: $(( free_kb / 1048576 )) GB free"
    fi

    echo ""
    echo "Ready commands:"
    echo "  sw_build       build all Docker images"
    echo "  sw_up          start core services"
    echo "  sw_migrate     run Django migrations"
    echo "  sw_test        run full pytest suite"
    echo "  sw_test_one    run a single test file"
    echo "  sw_shell       interactive shell in python-computation"
    echo "  sw_db          psql into PostGIS"
    echo "  sw_manage      django management commands"
    echo "  sw_logs        tail all service logs"
    echo "  sw_status      stack health overview"
    echo "  sw_down        stop and remove all volumes"
    echo "  sw_clean       clean unused Docker resources"
}

# -----------------------------------------------------------------
# Minimal aliases (available even without framework)
# -----------------------------------------------------------------
alias swtest='sw_test'
alias swshell='sw_shell'
alias swdb='sw_db'
alias swup='sw_up'
alias swdown='sw_down'
alias swlogs='sw_logs'

echo ""
echo "✅ SW dev environment loaded"
echo "   Run sw_doctor to check your setup, then sw_build → sw_up → sw_test"
echo ""
