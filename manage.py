#!/usr/bin/env python
"""Django's command-line utility for socialwarehouse."""
import os
import sys
from pathlib import Path

# GST submodule sys.path wiring. The load-bearing version of this lives
# in socialwarehouse/settings/base.py (post-ST3 / SW#141), so every
# entry point that loads settings (wsgi.py / asgi.py / pytest / ad-hoc
# settings.import) gets the wiring -- not just manage.py invocations.
#
# This duplicate insert is kept as defense-in-depth: it runs slightly
# earlier (before DJANGO_SETTINGS_MODULE is even set), which helps for
# the rare case where something imports from the GST app dir before
# settings is loaded. Safe to delete if settings.base.py is the sole
# source of truth and no pre-settings imports exist.
_GST_APP = Path(__file__).resolve().parent / "vendor" / "geodjango_simple_template" / "app" / "hellodjango"
if _GST_APP.is_dir() and str(_GST_APP) not in sys.path:
    sys.path.insert(0, str(_GST_APP))


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialwarehouse.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
