"""BLS QCEW open-data file downloader + parser.

# TODO (SU#533): LIFT TO SU
# This module's natural home is `siege_utilities.economic.bls.qcew`.
# It lives here today because SU doesn't have it yet and SW E Phase 1
# needs to ship. SU#533 tracks the lift. When that lands and SW bumps
# its SU pin, callers should switch to:
#
#   from siege_utilities.economic.bls.qcew import QCEWFiles
#
# and this module deletes.

BLS publishes QCEW open data files (no API key needed) at
data.bls.gov. Each quarter ships as a CSV inside a zip. This module
downloads, unzips, caches, and parses into a DataFrame normalized to
the shape `load_qcew` consumes.

Per E Q4 = (a) files-only path (no API key required).
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


logger = logging.getLogger(__name__)


# QCEW open-data URL pattern.
# Example: https://data.bls.gov/cew/data/files/2024/csv/2024_qtrly_singlefile.zip
QCEW_FILE_URL = "https://data.bls.gov/cew/data/files/{year}/csv/{year}_qtrly_singlefile.zip"

# Default cache location.
DEFAULT_CACHE_DIR = Path.home() / ".socialwarehouse" / "cache" / "qcew"


class QCEWFiles:
    """Thin wrapper around BLS QCEW open-data files.

    Network-only on the first download for a (year) tuple; cached on
    disk thereafter. parse() filters by (state_fips, quarter,
    naics_depth) without re-hitting the network.
    """

    def __init__(self, cache_dir: Optional[Path] = None, timeout: int = 120):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def download(self, year: int) -> Path:
        """Download (or return cached) the year's QCEW zip; return CSV path."""
        zip_path = self.cache_dir / f"{year}_qtrly_singlefile.zip"
        csv_path = self.cache_dir / f"{year}.qcew.csv"

        if csv_path.exists():
            logger.debug("QCEW year %s already cached at %s", year, csv_path)
            return csv_path

        url = QCEW_FILE_URL.format(year=year)
        logger.info("Downloading QCEW %s from %s", year, url)
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)

        with zipfile.ZipFile(zip_path) as zf:
            # BLS's zip carries one CSV; name varies slightly by year.
            csv_name = next(
                (n for n in zf.namelist() if n.endswith(".csv")),
                None,
            )
            if not csv_name:
                raise ValueError(f"No CSV found inside {zip_path}")
            with zf.open(csv_name) as src, open(csv_path, "wb") as dst:
                dst.write(src.read())
        zip_path.unlink(missing_ok=True)
        return csv_path

    def parse(
        self,
        csv_path: Path,
        *,
        year: int,
        quarter: int,
        state_fips: Optional[str] = None,
        naics_depth: int = 2,
    ) -> pd.DataFrame:
        """Parse a downloaded QCEW CSV into a normalized DataFrame.

        Filters:
          - quarter: the BLS `qtr` column matches; 1-4.
          - state_fips: if given, area_fips startswith state_fips.
          - naics_depth: keep only rows where industry_code length matches
            (NAICS 2-digit = sector level by default).

        Returns columns: area_fips, own_code, industry_code,
        agglvl_code, qtrly_estabs, month3_emplvl, total_qtrly_wages,
        avg_wkly_wage, year, qtr. Aliases to the load_qcew command's
        ingest shape.
        """
        df = pd.read_csv(csv_path, dtype={"area_fips": str, "industry_code": str})
        df = df[df["qtr"] == quarter]
        if state_fips:
            df = df[df["area_fips"].str.startswith(state_fips)]
        df = df[df["industry_code"].str.len() == naics_depth]
        return df.reset_index(drop=True)

    def load(
        self,
        *,
        year: int,
        quarter: int,
        state_fips: Optional[str] = None,
        naics_depth: int = 2,
    ) -> pd.DataFrame:
        """Download + parse in one call."""
        csv_path = self.download(year)
        return self.parse(
            csv_path,
            year=year, quarter=quarter,
            state_fips=state_fips, naics_depth=naics_depth,
        )
