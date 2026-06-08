"""Health checks for ``swh doctor``.

Each check function returns a ``CheckResult`` with status and detail.
Checks are designed to work without Django — they use ``swh.config``
(Pydantic settings) directly.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class Status(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str


def check_python_version() -> CheckResult:
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 11):
        return CheckResult("python_version", Status.PASS, version_str)
    return CheckResult("python_version", Status.FAIL, f"{version_str} (requires >= 3.11)")


def check_env_file() -> CheckResult:
    from swh.template import find_repo_root

    env_path = find_repo_root() / ".env"
    if not env_path.exists():
        return CheckResult("env_file", Status.FAIL, ".env not found — run `swh init`")

    content = env_path.read_text()
    required = ["POSTGRES_DB", "POSTGRES_USER", "DJANGO_SECRET_KEY"]
    missing = [k for k in required if k not in content]
    if missing:
        return CheckResult("env_file", Status.WARN, f"missing vars: {', '.join(missing)}")
    return CheckResult("env_file", Status.PASS, str(env_path))


def check_pgbouncer() -> CheckResult:
    """Verify PgBouncer is reachable and proxying connections."""
    try:
        from swh.config import settings

        import psycopg2

        conn = psycopg2.connect(settings.database.psycopg2_dsn, connect_timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            cur.fetchone()
            host = settings.database.host
            port = settings.database.port
            return CheckResult("pgbouncer", Status.PASS, f"{host}:{port}")
        finally:
            conn.close()
    except ImportError:
        return CheckResult("pgbouncer", Status.FAIL, "psycopg2 not installed")
    except Exception as exc:
        return CheckResult("pgbouncer", Status.WARN, f"not reachable: {exc}")


def check_postgis_connection() -> CheckResult:
    try:
        from swh.config import settings

        import psycopg2

        conn = psycopg2.connect(settings.database.direct_psycopg2_dsn, connect_timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT PostGIS_Version();")
            version = cur.fetchone()[0]
            return CheckResult("postgis", Status.PASS, f"PostGIS {version}")
        finally:
            conn.close()
    except ImportError:
        return CheckResult("postgis", Status.FAIL, "psycopg2 not installed")
    except Exception as exc:
        return CheckResult("postgis", Status.FAIL, str(exc))


def check_postgis_extensions() -> CheckResult:
    try:
        from swh.config import settings

        import psycopg2

        conn = psycopg2.connect(settings.database.direct_psycopg2_dsn, connect_timeout=5)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT extname FROM pg_extension "
                "WHERE extname IN ('postgis', 'postgis_topology') "
                "ORDER BY extname;"
            )
            installed = [row[0] for row in cur.fetchall()]
            expected = {"postgis"}
            missing = expected - set(installed)
            if missing:
                return CheckResult("postgis_extensions", Status.FAIL, f"missing: {', '.join(missing)}")
            return CheckResult("postgis_extensions", Status.PASS, ", ".join(installed))
        finally:
            conn.close()
    except ImportError:
        return CheckResult("postgis_extensions", Status.FAIL, "psycopg2 not installed")
    except Exception as exc:
        return CheckResult("postgis_extensions", Status.WARN, f"could not check: {exc}")


def check_redis() -> CheckResult:
    try:
        import redis as redis_lib

        broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        client = redis_lib.Redis.from_url(broker_url, socket_connect_timeout=3)
        client.ping()
        return CheckResult("redis", Status.PASS, broker_url)
    except ImportError:
        return CheckResult("redis", Status.WARN, "redis package not installed (optional)")
    except Exception as exc:
        return CheckResult("redis", Status.WARN, f"not reachable: {exc}")


def check_disk_space() -> CheckResult:
    from swh.template import find_repo_root

    root = find_repo_root()
    usage = shutil.disk_usage(root)
    free_gb = usage.free / (1024**3)
    if free_gb < 5:
        return CheckResult("disk_space", Status.WARN, f"{free_gb:.1f} GB free (< 5 GB)")
    return CheckResult("disk_space", Status.PASS, f"{free_gb:.1f} GB free")


def check_spark() -> CheckResult:
    try:
        import pyspark  # noqa: F401

        return CheckResult("spark", Status.PASS, f"pyspark {pyspark.__version__}")
    except ImportError:
        return CheckResult("spark", Status.WARN, "pyspark not installed (optional for Spark features)")


def check_migrations() -> CheckResult:
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "manage.py", "showmigrations", "--list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return CheckResult("migrations", Status.WARN, f"could not check: {result.stderr.strip()[:120]}")
        unapplied = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith("[ ]")
        ]
        if unapplied:
            return CheckResult("migrations", Status.WARN, f"{len(unapplied)} unapplied migration(s)")
        return CheckResult("migrations", Status.PASS, "all applied")
    except FileNotFoundError:
        return CheckResult("migrations", Status.WARN, "manage.py not found in CWD")
    except subprocess.TimeoutExpired:
        return CheckResult("migrations", Status.WARN, "timed out checking migrations")
    except Exception as exc:
        return CheckResult("migrations", Status.WARN, f"could not check: {exc}")


ALL_CHECKS: list[Callable[[], CheckResult]] = [
    check_python_version,
    check_env_file,
    check_pgbouncer,
    check_postgis_connection,
    check_postgis_extensions,
    check_redis,
    check_disk_space,
    check_spark,
    check_migrations,
]


def run_all_checks() -> list[CheckResult]:
    """Run every registered check and return the results."""
    return [check() for check in ALL_CHECKS]
