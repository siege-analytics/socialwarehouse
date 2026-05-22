"""Census TIGER/Line boundary shapefile source.

Reads from: https://www2.census.gov/geo/tiger/ (FTP)
Writes to:  local directory (for subsequent populate_boundaries loading)
Cadence:    Annual, typically Sept-Dec

Migrated from scripts/fetch_census_tiger.py during SW#35 unification.
Payload shape: int vintage year (e.g. 2024).
"""

from __future__ import annotations

import argparse
import ftplib
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from .base import Source

logger = logging.getLogger(__name__)

TIGER_FTP_HOST = "ftp2.census.gov"
TIGER_FTP_BASE = "/geo/tiger/"

# TIGER types used by siege_utilities populate_boundaries.
# Update this list when the boundary catalog gains new types
# (see docs/entities/boundary_catalog.md).
TIGER_TYPES = [
    "STATE", "COUNTY", "TRACT", "BG",
    "TABBLOCK20", "PLACE", "ZCTA520",
    "CD", "SLDL", "SLDU", "VTD",
    "CBSA", "UAC",
]


def _list_tiger_vintages() -> list[int]:
    """List TIGER vintage years available on the FTP server."""
    vintages: list[int] = []
    ftp = ftplib.FTP(TIGER_FTP_HOST, timeout=30)
    try:
        ftp.login()
        entries = ftp.nlst(TIGER_FTP_BASE)
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()

    for entry in entries:
        name = entry.rsplit("/", 1)[-1]
        match = re.match(r"TIGER(\d{4})", name)
        if match:
            vintages.append(int(match.group(1)))

    return sorted(vintages)


def _download_tiger_vintage(year: int, output_dir: Path, types: list[str]) -> list[Path]:
    """Download TIGER shapefiles for a vintage year."""
    output_dir.mkdir(parents=True, exist_ok=True)
    vintage_dir = output_dir / f"TIGER{year}"
    vintage_dir.mkdir(exist_ok=True)

    downloaded: list[Path] = []
    ftp = ftplib.FTP(TIGER_FTP_HOST, timeout=60)
    try:
        ftp.login()
        for tiger_type in types:
            remote_dir = f"{TIGER_FTP_BASE}TIGER{year}/{tiger_type}"
            try:
                entries = ftp.nlst(remote_dir)
            except ftplib.error_perm:
                logger.warning("Directory not found: %s (may not exist for %d)", remote_dir, year)
                continue

            type_dir = vintage_dir / tiger_type
            type_dir.mkdir(exist_ok=True)

            zip_files = [e for e in entries if e.endswith(".zip")]
            logger.info("Downloading %d files for %s/%d", len(zip_files), tiger_type, year)

            for remote_path in zip_files:
                filename = remote_path.rsplit("/", 1)[-1]
                local_path = type_dir / filename

                if local_path.exists():
                    logger.debug("Already exists: %s", local_path)
                    continue

                with open(local_path, "wb") as f:
                    ftp.retrbinary(f"RETR {remote_path}", f.write)
                downloaded.append(local_path)
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()

    logger.info("Downloaded %d files for TIGER%d", len(downloaded), year)
    return downloaded


class CensusTigerSource(Source):
    name = "census-tiger"
    description = "Census TIGER/Line boundary shapefiles from ftp2.census.gov"
    default_state_file = Path("/tmp/tiger-fetch-state.txt")

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--tiger-output-dir", type=Path, default=Path("/data/spatial/tiger"),
                            help="TIGER: local directory to download shapefiles into")
        parser.add_argument("--tiger-types", nargs="+", default=None,
                            help="TIGER: limit to specific TIGER type names (default: all)")

    def check(self) -> tuple[bool, Any]:
        try:
            available = _list_tiger_vintages()
        except ftplib.all_errors as e:
            logger.error("TIGER FTP error during check: %s", e)
            raise

        if not available:
            logger.warning("No TIGER vintages found on FTP")
            return False, None

        latest = max(available)
        last_fetched = self._get_last_vintage()

        if last_fetched and latest <= last_fetched:
            logger.info("Latest TIGER vintage %d already fetched (last: %d)", latest, last_fetched)
            return False, None

        logger.info("New TIGER vintage available: %d (last fetched: %s)", latest, last_fetched or "never")
        return True, latest

    def fetch(self, payload: Any, args: argparse.Namespace) -> None:
        vintage = int(payload)
        output_dir = getattr(args, "tiger_output_dir", Path("/data/spatial/tiger"))
        types = getattr(args, "tiger_types", None) or TIGER_TYPES
        _download_tiger_vintage(vintage, output_dir, types)

    def load(self, payload: Any, args: argparse.Namespace) -> None:
        vintage = int(payload)
        manage_py = getattr(args, "manage_py", "manage.py")
        cmd = ["python", manage_py, "populate_boundaries",
               "--year", str(vintage), "--type", "all"]
        logger.info("Loading boundaries: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)

    def update_state(self, payload: Any) -> None:
        vintage = int(payload)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(str(vintage))

    def describe_payload(self, payload: Any) -> str:
        return f"TIGER {payload}"

    def _get_last_vintage(self) -> int | None:
        if self.state_file.exists():
            try:
                return int(self.state_file.read_text().strip())
            except ValueError:
                logger.warning("TIGER state file has non-int contents; treating as never-fetched")
                return None
        return None
