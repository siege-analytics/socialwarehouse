"""
Base Django settings for socialwarehouse.

These are the common settings shared across all environments.
Override in development.py, production.py, or test.py as needed.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Dev-only fallback. Production settings overrides this with a fail-fast
# os.environ["DJANGO_SECRET_KEY"] read (ST1 / SW#139); production deployments
# that forget the env var get a KeyError at startup rather than silently
# running with the insecure default below.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-in-production")
DEBUG = False
ALLOWED_HOSTS = []  # base intentionally has no hosts; environment overrides (development = ["*"], production = bracket-subscript env-var-required per ST1/ST2) (ST5 / SW#143)

INSTALLED_APPS = [
    # grappelli must precede django.contrib.admin (Grappelli requirement)
    "grappelli",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # Third party
    "rest_framework",
    "rest_framework_gis",
    # siege_utilities geographic models
    "siege_utilities.geo.django",
    # socialwarehouse apps
    "socialwarehouse.core",
    "socialwarehouse.agents",
    "socialwarehouse.political",
    "socialwarehouse.transactions",
    "socialwarehouse.events",
    "socialwarehouse.geo",
    "socialwarehouse.warehouse",
    "socialwarehouse.demographic",
    "socialwarehouse.economic",
    "socialwarehouse.civic",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "socialwarehouse.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.environ.get("POSTGRES_DB", "socialwarehouse"),
        "USER": os.environ.get("POSTGRES_USER", "socialwarehouse"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
    # A9 / SW#120: all api views require authentication. Default
    # authentication classes are DRF's built-in Session + Basic; a
    # token-based scheme can be added later by appending to this list
    # (e.g. 'rest_framework.authentication.TokenAuthentication' once
    # rest_framework.authtoken is wired into INSTALLED_APPS + migrated).
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}

# Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

STATIC_URL = "static/"

STATICFILES_DIRS = []

LOGS_DIRECTORY = BASE_DIR / "logs"
