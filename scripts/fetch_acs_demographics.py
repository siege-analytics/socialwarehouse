#!/usr/bin/env python3
"""Check Census API for new ACS 5-year estimate releases and download if available.

Reads from: Census API (api.census.gov)
Writes to:  PostGIS via populate_demographics management command
Schedule:   Monthly (ACS 5-year updates annually, typically Dec)

The Census Bureau releases new ACS 5-year estimates once per year.
This script checks if a new vintage year is available and, if so,
triggers the populate_demographics command to load it.

Exit codes:
  0 = new data loaded
  1 = no new data
  2 = error
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CENSUS_API_BASE = "https://api.census.gov/data.json"


def get_available_acs_vintages() -> list[int]:
    """Query Census API catalog for available ACS 5-year vintages."""
    import requests

    logger.info("Querying Census API catalog")
    resp = requests.get(CENSUS_API_BASE, timeout=30)
    resp.raise_for_status()
    catalog = resp.json()

    vintages = set()
    for dataset in catalog.get("dataset", []):
        title = dataset.get("title", "")
        if "American Community Survey: 5-Year" in title or "ACS 5-Year" in title:
            vintage = dataset.get("c_vintage")
            if vintage and str(vintage).isdigit():
                vintages.add(int(vintage))

    return sorted(vintages)


def get_last_loaded_vintage(state_file: Path) -> int | None:
    """Read the last-loaded ACS vintage from state file."""
    if state_file.exists():
        try:
            return int(state_file.read_text().strip())
        except ValueError:
            return None
    return None


def check_for_updates(state_file: Path) -> tuple[bool, int | None]:
    """Check if a new ACS 5-year vintage is available."""
    available = get_available_acs_vintages()
    if not available:
        logger.warning("No ACS vintages found in Census API catalog")
        return False, None

    latest = max(available)
    last_loaded = get_last_loaded_vintage(state_file)

    if last_loaded and latest <= last_loaded:
        logger.info("Latest ACS vintage %d already loaded (last: %d)", latest, last_loaded)
        return False, None

    logger.info("New ACS vintage available: %d (last loaded: %s)", latest, last_loaded or "never")
    return True, latest


def load_demographics(year: int, manage_py: str = "manage.py",
                      states: list[str] | None = None,
                      census_api_key: str | None = None) -> None:
    """Call populate_demographics to load ACS data into PostGIS."""
    cmd = ["python", manage_py, "populate_demographics", "--year", str(year), "--type", "tract"]

    if states:
        for state in states:
            state_cmd = cmd + ["--state", state]
            logger.info("Loading demographics: %s", " ".join(state_cmd))
            env = None
            if census_api_key:
                import os
                env = os.environ.copy()
                env["CENSUS_API_KEY"] = census_api_key
            subprocess.run(state_cmd, check=True, env=env)
    else:
        logger.info("Loading demographics: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)


def update_state(state_file: Path, vintage: int) -> None:
    """Record the last-loaded vintage year."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(str(vintage))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-file", type=Path, default=Path("/tmp/acs-fetch-state.txt"))
    parser.add_argument("--manage-py", default="manage.py")
    parser.add_argument("--states", nargs="+", default=None,
                        help="Load specific states only (FIPS or abbreviations)")
    parser.add_argument("--census-api-key", default=None,
                        help="Census API key (or set CENSUS_API_KEY env var)")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-year", type=int, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.force_year:
        year = args.force_year
        has_updates = True
    else:
        has_updates, year = check_for_updates(args.state_file)

    if args.check_only:
        print(f"NEW_DATA: ACS {year}" if has_updates else "NO_UPDATES")
        sys.exit(0 if has_updates else 1)

    if not has_updates:
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN: would load ACS %d demographics", year)
        sys.exit(0)

    load_demographics(year, args.manage_py, args.states, args.census_api_key)
    update_state(args.state_file, year)
    print(f"LOADED: ACS {year} demographics")


if __name__ == "__main__":
    main()
