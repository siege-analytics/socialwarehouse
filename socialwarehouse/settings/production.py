from .base import *  # noqa: F401,F403

# Fail-fast: production must define DJANGO_SECRET_KEY explicitly. A missing
# env var raises KeyError at startup rather than silently inheriting the
# insecure dev fallback from base.py. (ST1 / SW#139)
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # noqa: F405

DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")  # noqa: F405
