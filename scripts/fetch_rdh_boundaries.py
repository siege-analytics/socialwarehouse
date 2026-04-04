#!/usr/bin/env python3
"""Check Redistricting Data Hub for new boundary plan uploads.

Reads from: https://redistrictingdatahub.org/
Writes to:  local directory (for subsequent boundary loading)
Schedule:   Weekly (plans upload irregularly — court orders, new cycles)

After download, new boundary shapefiles can be loaded via:
  python manage.py populate_boundaries --source rdh --year YYYY

Exit codes:
  0 = new data found/downloaded
  1 = no new data
  2 = error
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# RDH catalog endpoint (may need API key for full access)
RDH_CATALOG_URL = "https://redistrictingdatahub.org/wp-json/download/v1/catalog"

# Plan types we care about
PLAN_TYPES = ["congress", "state_senate", "state_house"]

# Priority states for LegiNation and high-value coverage
PRIORITY_STATES = [
    "NJ", "MA", "NY",
    "FL", "TX", "CA", "PA", "OH", "WA", "IL", "CO",
]


def fetch_catalog(catalog_url: str = RDH_CATALOG_URL) -> list[dict]:
    """Fetch the RDH data catalog."""
    import requests

    logger.info("Fetching RDH catalog from %s", catalog_url)
    resp = requests.get(catalog_url, timeout=30)

    if resp.status_code == 200:
        try:
            return resp.json()
        except json.JSONDecodeError:
            logger.warning("RDH catalog returned non-JSON response")
            return []
    else:
        logger.warning("RDH catalog returned status %d", resp.status_code)
        return []


def filter_boundary_plans(catalog: list[dict], states: list[str] | None = None,
                          plan_types: list[str] | None = None) -> list[dict]:
    """Filter catalog to redistricting boundary plans for target states."""
    if plan_types is None:
        plan_types = PLAN_TYPES

    filtered = []
    for entry in catalog:
        name = entry.get("name", entry.get("title", "")).lower()
        state = entry.get("state", "")
        data_type = entry.get("type", entry.get("data_type", ""))

        is_boundary = any(pt in name or pt in data_type for pt in plan_types)
        is_target_state = states is None or state in states

        if is_boundary and is_target_state:
            filtered.append(entry)

    return filtered


def check_for_updates(state_file: Path, states: list[str] | None = None) -> tuple[bool, list[dict]]:
    """Check if RDH has new boundary plans since last fetch."""
    catalog = fetch_catalog()

    if not catalog:
        return False, []

    plans = filter_boundary_plans(catalog, states)

    known_ids = set()
    if state_file.exists():
        try:
            last_check = json.loads(state_file.read_text())
            known_ids = set(last_check.get("known_ids", []))
        except (json.JSONDecodeError, KeyError):
            pass

    new_plans = [p for p in plans if p.get("id", p.get("name", "")) not in known_ids]

    if new_plans:
        logger.info("Found %d new boundary plans", len(new_plans))
        return True, new_plans
    else:
        logger.info("No new boundary plans (checked %d total)", len(plans))
        return False, []


def download_plans(plans: list[dict], output_dir: Path) -> list[Path]:
    """Download boundary plan files."""
    import requests

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for plan in plans:
        url = plan.get("download_url", plan.get("url", ""))
        name = plan.get("name", plan.get("title", "unknown"))

        if not url:
            logger.warning("No download URL for plan: %s", name)
            continue

        filename = f"{name.replace(' ', '_').replace('/', '-')}.zip"
        output_path = output_dir / filename

        if output_path.exists():
            continue

        logger.info("Downloading: %s", name)
        try:
            resp = requests.get(url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded.append(output_path)
        except Exception as e:
            logger.error("Failed to download %s: %s", name, e)

    return downloaded


def update_state(state_file: Path, plans: list[dict]) -> None:
    """Record known plan IDs."""
    known_ids = set()
    if state_file.exists():
        try:
            existing = json.loads(state_file.read_text())
            known_ids = set(existing.get("known_ids", []))
        except (json.JSONDecodeError, KeyError):
            pass

    for plan in plans:
        known_ids.add(plan.get("id", plan.get("name", "")))

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "known_ids": sorted(known_ids),
        "last_checked": datetime.utcnow().isoformat(),
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=Path("/data/spatial/rdh"))
    parser.add_argument("--state-file", type=Path, default=Path("/tmp/rdh-fetch-state.json"))
    parser.add_argument("--states", nargs="+", default=PRIORITY_STATES)
    parser.add_argument("--all-states", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    states = None if args.all_states else args.states
    has_updates, new_plans = check_for_updates(args.state_file, states)

    if args.check_only:
        if has_updates:
            print(f"NEW_DATA: {len(new_plans)} plans")
            for p in new_plans:
                print(f"  {p.get('state', '??')}: {p.get('name', p.get('title', 'unknown'))}")
        else:
            print("NO_UPDATES")
        sys.exit(0 if has_updates else 1)

    if not has_updates:
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN: would download %d plans", len(new_plans))
        sys.exit(0)

    downloaded = download_plans(new_plans, args.output_dir)
    update_state(args.state_file, new_plans)
    print(f"DOWNLOADED: {len(downloaded)} boundary plan files")


if __name__ == "__main__":
    main()
