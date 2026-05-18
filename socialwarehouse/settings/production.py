from .base import *  # noqa: F401,F403

# Fail-fast: production must define DJANGO_SECRET_KEY explicitly. A missing
# env var raises KeyError at startup rather than silently inheriting the
# insecure dev fallback from base.py. (ST1 / SW#139)
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # noqa: F405

# Fail-fast on ALLOWED_HOSTS too. Pre-fix: os.environ.get("ALLOWED_HOSTS", "").split(",")
# returned [""] when the env var was unset (truthy, matches no hosts, surfaces
# as confusing DisallowedHost on every request). Now: bracket subscript raises
# KeyError at startup; blanks are filtered to allow comma-trailing forms like
# "a.com,b.com,". (ST2 / SW#140)
ALLOWED_HOSTS = [h.strip() for h in os.environ["ALLOWED_HOSTS"].split(",") if h.strip()]  # noqa: F405
if not ALLOWED_HOSTS:
    raise RuntimeError(
        "ALLOWED_HOSTS env var is set but parses to no host names "
        "(e.g. empty string or only commas). Provide at least one host."
    )

# Fail-fast on POSTGRES_PASSWORD. Pre-fix: empty-string default surfaced as
# opaque PG connection error mid-query. Now: required in production.
# base.py retains the dev fallback so local development continues to work.
# (ST4 / SW#142)
DATABASES["default"]["PASSWORD"] = os.environ["POSTGRES_PASSWORD"]  # noqa: F405

DEBUG = False
