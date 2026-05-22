"""ACS 5-year demographic vintage source.

Reads from: Census API (api.census.gov)
Writes to:  PostGIS via populate_demographics management command
Cadence:    Annual, typically December

Migrated from scripts/fetch_acs_demographics.py during SW#35 unification.
Payload shape: int vintage year (e.g. 2023).
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from .base import Source

logger = logging.getLogger(__name__)

CENSUS_API_BASE = "https://api.census.gov/data.json"


def _get_available_acs_vintages() -> list[int]:
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


class ACSSource(Source):
    name = "acs"
    description = "ACS 5-year demographic estimates from the Census API"
    default_state_file = Path("/tmp/acs-fetch-state.txt")

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--states", nargs="+", default=None,
                            help="ACS: load specific states only (FIPS or abbreviations)")
        parser.add_argument("--census-api-key", default=None,
                            help="ACS: Census API key (or set CENSUS_API_KEY env var)")

    def check(self) -> tuple[bool, Any]:
        available = _get_available_acs_vintages()
        if not available:
            logger.warning("No ACS vintages found in Census API catalog")
            return False, None

        latest = max(available)
        last_loaded = self._get_last_vintage()

        if last_loaded and latest <= last_loaded:
            logger.info("Latest ACS vintage %d already loaded (last: %d)", latest, last_loaded)
            return False, None

        logger.info("New ACS vintage available: %d (last loaded: %s)", latest, last_loaded or "never")
        return True, latest

    def fetch(self, payload: Any, args: argparse.Namespace) -> None:
        # ACS is API-pulled by the load command; no separate fetch step.
        logger.debug("ACS fetch is folded into load (API-driven); no separate download.")

    def load(self, payload: Any, args: argparse.Namespace) -> None:
        vintage = int(payload)
        manage_py = getattr(args, "manage_py", "manage.py")
        states = getattr(args, "states", None)
        census_api_key = getattr(args, "census_api_key", None)

        env = None
        if census_api_key:
            env = os.environ.copy()
            env["CENSUS_API_KEY"] = census_api_key

        cmd_base = ["python", manage_py, "populate_demographics",
                    "--year", str(vintage), "--type", "tract"]

        if states:
            for state in states:
                cmd = cmd_base + ["--state", state]
                logger.info("Loading demographics: %s", " ".join(cmd))
                subprocess.run(cmd, check=True, env=env)
        else:
            logger.info("Loading demographics: %s", " ".join(cmd_base))
            subprocess.run(cmd_base, check=True, env=env)

    def update_state(self, payload: Any) -> None:
        vintage = int(payload)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(str(vintage))

    def describe_payload(self, payload: Any) -> str:
        return f"ACS {payload}"

    def _get_last_vintage(self) -> int | None:
        if self.state_file.exists():
            try:
                return int(self.state_file.read_text().strip())
            except ValueError:
                logger.warning("ACS state file has non-int contents; treating as never-loaded")
                return None
        return None
