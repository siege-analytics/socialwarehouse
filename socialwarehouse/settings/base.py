"""
Base Django settings for socialwarehouse.

These are the common settings shared across all environments.
Override in development.py, production.py, or test.py as needed.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-in-production")
DEBUG = False
ALLOWED_HOSTS = []

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
    "socialwarehouse.geo",
    "socialwarehouse.warehouse",
    # GST apps (via vendor/geodjango_simple_template/ submodule, P1B-B #68)
    "locations",
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
}

# Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

STATIC_URL = "static/"

# Pull GST's project-level staticfiles into Django's collectstatic surface.
# GST's per-app static dirs are picked up via APP_DIRS automatically.
STATICFILES_DIRS = [
    BASE_DIR / "vendor" / "geodjango_simple_template" / "app" / "hellodjango" / "staticfiles",
]

# ---------------------------------------------------------------------------
# GST-required settings (read at module-load by hellodjango/utilities/* and
# hellodjango/locations/*). Mirrored from
# vendor/geodjango_simple_template/app/hellodjango/hellodjango/settings/
# (path_settings.py, generic_gis_settings.py, vector_data_file_settings.py,
# api_settings/nominatim_geocoding.py). Defined inline rather than imported
# to avoid pulling in GST's other settings modules (which include statsmodels
# and Django config that would conflict with SW's).
# ---------------------------------------------------------------------------

# GST data directory layout. GST modules join these into deeper paths.
# These point under the SW repo root so GST's data lives alongside SW data.
_GST_DATA_DIR = BASE_DIR / "data"
SPATIAL_DATA_SUBDIRECTORY = _GST_DATA_DIR / "spatial"
TABULAR_DATA_SUBDIRECTORY = _GST_DATA_DIR / "tabular"
VECTOR_SPATIAL_DATA_SUBDIRECTORY = SPATIAL_DATA_SUBDIRECTORY / "vector"
RASTER_SPATIAL_DATA_SUBDIRECTORY = SPATIAL_DATA_SUBDIRECTORY / "raster"
POINTCLOUD_SPATIAL_DATA_SUBDIRECTORY = SPATIAL_DATA_SUBDIRECTORY / "pointcloud"
CENSUS_TIGER_LINE_DATA = VECTOR_SPATIAL_DATA_SUBDIRECTORY / "census_tiger"
LOGS_DIRECTORY = BASE_DIR / "logs"
NECESSARY_PATHS = [
    _GST_DATA_DIR,
    SPATIAL_DATA_SUBDIRECTORY,
    TABULAR_DATA_SUBDIRECTORY,
    VECTOR_SPATIAL_DATA_SUBDIRECTORY,
    RASTER_SPATIAL_DATA_SUBDIRECTORY,
    POINTCLOUD_SPATIAL_DATA_SUBDIRECTORY,
    CENSUS_TIGER_LINE_DATA,
    LOGS_DIRECTORY,
]

# GST projection constants (from GST generic_gis_settings.py).
DEFAULT_PROJECTION_NUMBER = 4326
PREFERRED_PROJECTION_FOR_US_DISTANCE_SEARCH = 5070

# GST nominatim API constants (from GST api_settings/nominatim_geocoding.py).
NOMINATIM_API_BASE_URL = "https://nominatim.openstreetmap.org/search?"
NOMINATIM_USER_AGENT = "socialwarehouse"
NOMINATIM_LATITUDE_VARIABLE = "lat"
NOMINATIM_LONGITUDE_VARIABLE = "lon"

# GST vector file extensions (from GST vector_data_file_settings.py).
VALID_VECTOR_FILE_EXTENSIONS = [
    ".dwg", ".dxf", ".gdb", ".geojson", ".gpkg", ".json",
    ".kml", ".kmz", ".shp", ".swm2", ".swmaps", ".swmz",
]
