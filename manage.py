#!/usr/bin/env python
"""Django's command-line utility for socialwarehouse."""
import os
import sys
from pathlib import Path

# GST submodule: vendor/geodjango_simple_template/app/ holds GST's
# `hellodjango` Django package. Inserted at the start of sys.path so
# `import hellodjango.locations` etc. resolves once the submodule is
# initialised. P1B-A wires the path; P1B-B will add GST apps to
# INSTALLED_APPS. See plans/p1b-gst-submodule-design.md (#66).
_GST_APP = Path(__file__).resolve().parent / "vendor" / "geodjango_simple_template" / "app"
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
