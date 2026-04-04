#!/usr/bin/env python3
"""Check Census TIGER/Line FTP for new vintage year data and download if available.

Reads from: https://www2.census.gov/geo/tiger/
Writes to:  local directory (for subsequent populate_boundaries loading)
Schedule:   Monthly (Census releases annually, typically Sept-Dec)

After download, call siege_utilities management commands to load:
  python manage.py populate_boundaries --year YYYY --type all

Exit codes:
  0 = new data downloaded (or --check-only found updates)
  1 = no new data
  2 = error
"""

import argparse
import ftplib
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

TIGER_FTP_HOST = "ftp2.census.gov"
TIGER_FTP_BASE = "/geo/tiger/"

# TIGER types used by siege_utilities populate_boundaries
TIGER_TYPES = [
    "STATE", "COUNTY", "TRACT", "BG",
    "TABBLOCK20", "PLACE", "ZCTA520",
    "CD", "SLDL", "SLDU", "VTD",
    "CBSA", "UAC",
]


def get_available_vintages() -> list[int]:
    """List TIGER vintage years available on the FTP server."""
    vintages = []
    try:
        ftp = ftplib.FTP(TIGER_FTP_HOST, timeout=30)
        ftp.login()
        entries = ftp.nlst(TIGER_FTP_BASE)
        ftp.quit()

        for entry in entries:
            name = entry.rsplit("/", 1)[-1]
            match = re.match(r"TIGER(\d{4})", name)
            if match:
                vintages.append(int(match.group(1)))

    except ftplib.all_errors as e:
        logger.error("FTP error: %s", e)
        raise

    return sorted(vintages)


def get_last_fetched_vintage(state_file: Path) -> int | None:
    """Read the last-fetched vintage year from state file."""
    if state_file.exists():
        try:
            return int(state_file.read_text().strip())
        except ValueError:
            return None
    return None


def check_for_updates(state_file: Path) -> tuple[bool, int | None]:
    """Check if a new TIGER vintage year is available."""
    available = get_available_vintages()
    if not available:
        logger.warning("No TIGER vintages found on FTP")
        return False, None

    latest = max(available)
    last_fetched = get_last_fetched_vintage(state_file)

    if last_fetched and latest <= last_fetched:
        logger.info("Latest vintage %d already fetched (last: %d)", latest, last_fetched)
        return False, None

    logger.info("New vintage available: TIGER%d (last fetched: %s)", latest, last_fetched or "never")
    return True, latest


def download_vintage(year: int, output_dir: Path, types: list[str] | None = None) -> list[Path]:
    """Download TIGER shapefiles for a vintage year."""
    if types is None:
        types = TIGER_TYPES

    output_dir.mkdir(parents=True, exist_ok=True)
    vintage_dir = output_dir / f"TIGER{year}"
    vintage_dir.mkdir(exist_ok=True)

    downloaded = []
    ftp = ftplib.FTP(TIGER_FTP_HOST, timeout=60)
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

    ftp.quit()
    logger.info("Downloaded %d files for TIGER%d", len(downloaded), year)
    return downloaded


def load_boundaries(year: int, manage_py: str = "manage.py") -> None:
    """Call populate_boundaries to load downloaded TIGER data into PostGIS."""
    cmd = ["python", manage_py, "populate_boundaries", "--year", str(year), "--type", "all"]
    logger.info("Loading boundaries: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def update_state(state_file: Path, vintage: int) -> None:
    """Record the last-fetched vintage year."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(str(vintage))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=Path("/data/spatial/tiger"))
    parser.add_argument("--state-file", type=Path, default=Path("/tmp/tiger-fetch-state.txt"))
    parser.add_argument("--types", nargs="+", default=None,
                        help=f"TIGER types (default: all). Options: {', '.join(TIGER_TYPES)}")
    parser.add_argument("--load", action="store_true",
                        help="After download, run populate_boundaries to load into PostGIS")
    parser.add_argument("--manage-py", default="manage.py",
                        help="Path to Django manage.py (for --load)")
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
        print(f"NEW_DATA: TIGER{year}" if has_updates else "NO_UPDATES")
        sys.exit(0 if has_updates else 1)

    if not has_updates:
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN: would download TIGER%d to %s", year, args.output_dir)
        sys.exit(0)

    downloaded = download_vintage(year, args.output_dir, args.types)

    if args.load:
        load_boundaries(year, args.manage_py)

    update_state(args.state_file, year)
    print(f"DOWNLOADED: {len(downloaded)} files for TIGER{year}")


if __name__ == "__main__":
    main()
