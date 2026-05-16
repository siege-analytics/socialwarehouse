#!/usr/bin/env python
"""Django's command-line utility for socialwarehouse."""
import os
import sys
from pathlib import Path

# GST submodule: vendor/geodjango_simple_template/app/hellodjango/ holds
# GST's Django apps. Inserted at the start of sys.path so `import
# locations` resolves once the submodule is initialised. (GST configures
# its apps with bare names like 'locations', not 'hellodjango.locations',
# matching how GST itself runs from app/hellodjango/ as cwd.)
# P1B-A wired the path (one level too high); P1B-B (#68) corrects it
# and adds GST apps to INSTALLED_APPS. See
# plans/p1b-b-absorb-gst-apps-design.md.
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
