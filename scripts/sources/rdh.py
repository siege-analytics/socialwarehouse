"""Redistricting Data Hub boundary plan source.

Reads from: https://redistrictingdatahub.org/
Writes to:  local directory (for subsequent boundary loading)
Cadence:    Irregular (court orders, new cycles); polled weekly

Migrated from scripts/fetch_rdh_boundaries.py during SW#35 unification.
Payload shape: list[dict] of new plan catalog entries (not yet in
state file).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Source

logger = logging.getLogger(__name__)

RDH_CATALOG_URL = "https://redistrictingdatahub.org/wp-json/download/v1/catalog"

PLAN_TYPES = ["congress", "state_senate", "state_house"]

PRIORITY_STATES = [
    "NJ", "MA", "NY",
    "FL", "TX", "CA", "PA", "OH", "WA", "IL", "CO",
]


def _fetch_catalog(catalog_url: str = RDH_CATALOG_URL) -> list[dict]:
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


def _filter_boundary_plans(catalog: list[dict], states: list[str] | None,
                           plan_types: list[str]) -> list[dict]:
    """Filter catalog to redistricting boundary plans for target states."""
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


def _plan_id(plan: dict) -> str:
    """Stable identity for a plan (used for known-set comparison)."""
    return str(plan.get("id", plan.get("name", "")))


def _download_plans(plans: list[dict], output_dir: Path) -> list[Path]:
    """Download boundary plan files via siege_utilities retry-aware helper."""
    from siege_utilities.files.remote import download_file_with_retry

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

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
        result = download_file_with_retry(
            url=url,
            local_filename=str(output_path),
            max_retries=3,
            retry_delay=5,
        )
        if result:
            downloaded.append(Path(result))
        else:
            logger.error(
                "Failed to download %s after retries; see siege_utilities "
                "log for per-attempt detail.",
                name,
            )

    return downloaded


class RDHSource(Source):
    name = "rdh"
    description = "Redistricting Data Hub plan uploads (boundary catalog by state)"
    default_state_file = Path("/tmp/rdh-fetch-state.json")

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--rdh-output-dir", type=Path, default=Path("/data/spatial/rdh"),
                            help="RDH: local directory for downloaded plans")
        parser.add_argument("--rdh-states", nargs="+", default=PRIORITY_STATES,
                            help="RDH: state filter (default: priority list)")
        parser.add_argument("--rdh-all-states", action="store_true",
                            help="RDH: ignore state filter, include all states")
        parser.add_argument("--rdh-plan-types", nargs="+", default=PLAN_TYPES,
                            help="RDH: plan types to include (default: congress, state_senate, state_house)")

    def check(self) -> tuple[bool, Any]:
        # Defer reading the args namespace here — orchestrator passes args
        # to fetch/load, not to check. Use defaults for the catalog scan.
        catalog = _fetch_catalog()
        if not catalog:
            return False, []

        plans = _filter_boundary_plans(catalog, states=None, plan_types=PLAN_TYPES)
        known = self._get_known_ids()
        new_plans = [p for p in plans if _plan_id(p) not in known]

        if new_plans:
            logger.info("Found %d new RDH plans", len(new_plans))
            return True, new_plans

        logger.info("No new RDH plans (checked %d total)", len(plans))
        return False, []

    def fetch(self, payload: Any, args: argparse.Namespace) -> None:
        plans = list(payload)
        # Re-apply per-call state filtering at fetch time so the user's
        # --rdh-states / --rdh-plan-types choice narrows what we actually
        # download (check found everything; fetch downloads what the user
        # asked for).
        states = None if getattr(args, "rdh_all_states", False) else getattr(args, "rdh_states", PRIORITY_STATES)
        plan_types = getattr(args, "rdh_plan_types", PLAN_TYPES)
        filtered = _filter_boundary_plans(plans, states, plan_types)

        output_dir = getattr(args, "rdh_output_dir", Path("/data/spatial/rdh"))
        _download_plans(filtered, output_dir)

    def load(self, payload: Any, args: argparse.Namespace) -> None:
        # RDH downloads land in a directory; the boundary-loading happens
        # via populate_boundaries with --source rdh in a separate step
        # (per the legacy script's docstring). v1 leaves load as a no-op
        # here so the cron / Rundeck job orchestrator can choose when to
        # invoke populate_boundaries against the dropped files.
        logger.info("RDH load is downstream: invoke `python manage.py populate_boundaries --source rdh` against %s when ready.",
                    getattr(args, "rdh_output_dir", Path("/data/spatial/rdh")))

    def update_state(self, payload: Any) -> None:
        new_ids = {_plan_id(p) for p in payload}
        known = self._get_known_ids() | new_ids

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "known_ids": sorted(known),
            "last_checked": datetime.utcnow().isoformat(),
        }, indent=2))

    def describe_payload(self, payload: Any) -> str:
        count = len(list(payload))
        return f"{count} new RDH plan{'s' if count != 1 else ''}"

    def _get_known_ids(self) -> set[str]:
        if not self.state_file.exists():
            return set()
        try:
            data = json.loads(self.state_file.read_text())
            return set(data.get("known_ids", []))
        except (json.JSONDecodeError, KeyError):
            logger.warning("RDH state file unreadable; treating as no-known-plans")
            return set()
