#!/usr/bin/env python3
"""Unified fetch entry point. Dispatches to a registered Source.

Usage:
  python scripts/fetch.py SOURCE [--check-only] [--dry-run] [--force-vintage YYYY]
  python scripts/fetch.py --check-all
  python scripts/fetch.py --list

Sources are registered in scripts/sources/__init__.py's SOURCES map.
Each source defines its own check/fetch/load lifecycle and may add
source-specific CLI args (see ``Source.add_arguments``).

Exit codes:
  0 = new data fetched/loaded (or --check-only found updates)
  1 = no new data
  2 = error
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sources import SOURCES, Source

logger = logging.getLogger(__name__)


def _common_args(parser: argparse.ArgumentParser) -> None:
    """Add args common to every source."""
    parser.add_argument("--state-file", type=Path, default=None,
                        help="Override default state-file path for the source")
    parser.add_argument("--manage-py", default="manage.py",
                        help="Path to Django manage.py (default: manage.py)")
    parser.add_argument("--check-only", action="store_true",
                        help="Print update status and exit (no fetch/load)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip fetch + load, but still print what would happen")
    parser.add_argument("--force-vintage", type=int, default=None,
                        help="Skip check; force fetch/load for the given vintage "
                             "(vintage-based sources only)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable DEBUG logging")


def _list_sources() -> int:
    """Print the registered source slugs + descriptions."""
    width = max(len(name) for name in SOURCES) if SOURCES else 0
    print("Registered sources:")
    for name, cls in sorted(SOURCES.items()):
        print(f"  {name:<{width}}  {cls.description}")
    return 0


def _run_source(source: Source, args: argparse.Namespace) -> int:
    """Run the check -> fetch -> load -> update_state lifecycle for one source.

    Returns the appropriate process exit code (0 / 1 / 2)."""
    if args.force_vintage is not None:
        payload = args.force_vintage
        has_update = True
        logger.info("[%s] --force-vintage %d: skipping check", source.name, args.force_vintage)
    else:
        try:
            has_update, payload = source.check()
        except Exception as e:
            logger.error("[%s] check failed: %s", source.name, e)
            return 2

    if args.check_only:
        if has_update:
            print(f"NEW_DATA [{source.name}]: {source.describe_payload(payload)}")
            return 0
        else:
            print(f"NO_UPDATES [{source.name}]")
            return 1

    if not has_update:
        return 1

    if args.dry_run:
        logger.info("[%s] DRY RUN: would fetch + load %s",
                    source.name, source.describe_payload(payload))
        return 0

    try:
        source.fetch(payload, args)
        source.load(payload, args)
        source.update_state(payload)
    except Exception as e:
        logger.error("[%s] fetch/load failed: %s", source.name, e)
        return 2

    print(f"LOADED [{source.name}]: {source.describe_payload(payload)}")
    return 0


def _run_check_all(args: argparse.Namespace) -> int:
    """Run check (only) against every registered source. Exit 0 if any update."""
    any_update = False
    failures = 0
    for name in sorted(SOURCES):
        cls = SOURCES[name]
        source = cls(state_file=args.state_file)
        try:
            has_update, payload = source.check()
        except Exception as e:
            logger.error("[%s] check failed: %s", name, e)
            failures += 1
            continue

        if has_update:
            print(f"NEW_DATA [{name}]: {source.describe_payload(payload)}")
            any_update = True
        else:
            print(f"NO_UPDATES [{name}]")

    if failures:
        return 2
    return 0 if any_update else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Top-level: pick a source OR meta-action.
    parser.add_argument("source", nargs="?", default=None,
                        choices=sorted(SOURCES),
                        help="Source slug (see --list for options)")
    parser.add_argument("--check-all", action="store_true",
                        help="Run check against every registered source")
    parser.add_argument("--list", action="store_true",
                        help="List registered sources and exit")

    _common_args(parser)

    # Aggregate source-specific args from every registered source so
    # ``--help`` shows them all. This is fine because they're namespaced
    # by source-prefix in each subclass's add_arguments (e.g. --tiger-*,
    # --rdh-*, --census-api-key).
    for cls in SOURCES.values():
        cls.add_arguments(parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.list:
        return _list_sources()

    if args.check_all:
        return _run_check_all(args)

    if args.source is None:
        parser.print_help()
        return 2

    cls = SOURCES[args.source]
    source = cls(state_file=args.state_file)
    return _run_source(source, args)


if __name__ == "__main__":
    sys.exit(main())
