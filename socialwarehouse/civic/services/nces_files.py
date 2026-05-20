"""NCES CCD + EDGE file downloader + parser.

# TODO (SU#534): LIFT TO SU
# This module's natural home is `siege_utilities.education.nces`.
# It lives here today because SU doesn't have it yet and SW F Phase 1a
# needs to ship. SU#534 tracks the lift. When that lands and SW bumps
# its SU pin, callers should switch to:
#
#   from siege_utilities.education.nces import NCESFiles
#
# and this module deletes.

NCES publishes Common Core of Data (CCD) and Education Demographic
and Geographic Estimates (EDGE) as open data files (no API key).
This module covers Phase 1a's CCD district-level needs:

- LEA Directory file (district names, types, addresses)
- Nonfiscal Survey: enrollment + staff
- F-33 Finance Survey: revenues + expenditures

Phase 1b will add CCD school-level. Phase 1c will add EDGE
demographic estimates per district.

NCES URLs and file names change yearly; the helper accepts a
school-year string like "2022-23" and resolves to the right URL.
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

# Cache location.
DEFAULT_CACHE_DIR = Path.home() / ".socialwarehouse" / "cache" / "nces"

# NCES URL patterns (subset — Phase 1a). These URLs evolve; ops can
# override via the `url_override` kwarg if NCES reshapes a release.
CCD_DIRECTORY_URL = (
    "https://nces.ed.gov/ccd/data/zip/ccd_lea_029_{end_2digit}_l_1a.zip"
)
CCD_NONFISCAL_URL = (
    "https://nces.ed.gov/ccd/data/zip/ccd_lea_052_{end_2digit}_l_1a.zip"
)
CCD_F33_URL = (
    "https://nces.ed.gov/ccd/data/zip/sdf{end_2digit}_1a.zip"
)

# School-level CCD files (per F Phase 1b).
CCD_SCHOOL_DIRECTORY_URL = (
    "https://nces.ed.gov/ccd/data/zip/ccd_sch_029_{end_2digit}_l_1a.zip"
)
CCD_SCHOOL_NONFISCAL_URL = (
    "https://nces.ed.gov/ccd/data/zip/ccd_sch_052_{end_2digit}_l_1a.zip"
)

# EDGE per-district ACS-derived demographics (Phase 1c).
# Example: EDGE_ACS_2018-22_DISTRICT.csv
EDGE_DISTRICT_DEMOGRAPHICS_URL = (
    "https://nces.ed.gov/programs/edge/data/EDGE_ACS_{acs_endpoint}_DISTRICT.csv"
)


class NCESFiles:
    """Thin wrapper around NCES CCD open data files (Phase 1a)."""

    def __init__(self, cache_dir: Optional[Path] = None, timeout: int = 120):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    @staticmethod
    def _parse_school_year(school_year: str) -> tuple[int, int]:
        """'2022-23' -> (2022, 2023); '2099-00' -> (2099, 2100).

        School years span two consecutive calendar years; the '-NN'
        suffix is decorative for the human reader. We just take the
        start year and add 1.
        """
        if "-" not in school_year:
            raise ValueError(f"school_year must be like '2022-23'; got {school_year!r}")
        start_str, _ = school_year.split("-", 1)
        start = int(start_str)
        return start, start + 1

    def _download_zip(self, url: str, cache_name: str) -> Path:
        """Download + cache one NCES zip; return CSV path inside cache_dir."""
        csv_path = self.cache_dir / f"{cache_name}.csv"
        if csv_path.exists():
            return csv_path
        logger.info("Downloading NCES file: %s", url)
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = next((n for n in zf.namelist() if n.endswith((".csv", ".txt"))), None)
            if not csv_name:
                raise ValueError(f"No CSV/TXT inside {url}")
            with zf.open(csv_name) as src, open(csv_path, "wb") as dst:
                dst.write(src.read())
        return csv_path

    def load_ccd_directory(self, school_year: str) -> pd.DataFrame:
        start, end = self._parse_school_year(school_year)
        url = CCD_DIRECTORY_URL.format(end_2digit=str(end)[-2:])
        path = self._download_zip(url, f"ccd_lea_directory_{school_year}")
        return pd.read_csv(path, dtype={"LEAID": str, "STATEFIPS": str}, low_memory=False)

    def load_ccd_nonfiscal(self, school_year: str) -> pd.DataFrame:
        start, end = self._parse_school_year(school_year)
        url = CCD_NONFISCAL_URL.format(end_2digit=str(end)[-2:])
        path = self._download_zip(url, f"ccd_lea_nonfiscal_{school_year}")
        return pd.read_csv(path, dtype={"LEAID": str}, low_memory=False)

    def load_ccd_finance(self, school_year: str) -> pd.DataFrame:
        start, end = self._parse_school_year(school_year)
        url = CCD_F33_URL.format(end_2digit=str(end)[-2:])
        path = self._download_zip(url, f"ccd_lea_finance_{school_year}")
        return pd.read_csv(path, dtype={"LEAID": str}, low_memory=False)

    # ── School-level loaders (Phase 1b) ───────────────────────────────

    def load_ccd_school_directory(self, school_year: str) -> pd.DataFrame:
        start, end = self._parse_school_year(school_year)
        url = CCD_SCHOOL_DIRECTORY_URL.format(end_2digit=str(end)[-2:])
        path = self._download_zip(url, f"ccd_sch_directory_{school_year}")
        return pd.read_csv(
            path,
            dtype={"NCESSCH": str, "LEAID": str, "STATEFIPS": str},
            low_memory=False,
        )

    def load_ccd_school_nonfiscal(self, school_year: str) -> pd.DataFrame:
        start, end = self._parse_school_year(school_year)
        url = CCD_SCHOOL_NONFISCAL_URL.format(end_2digit=str(end)[-2:])
        path = self._download_zip(url, f"ccd_sch_nonfiscal_{school_year}")
        return pd.read_csv(path, dtype={"NCESSCH": str, "LEAID": str}, low_memory=False)

    # ── EDGE per-district demographics (Phase 1c) ─────────────────────

    def load_edge_district_demographics(self, acs_endpoint: str) -> pd.DataFrame:
        """Load EDGE per-school-district demographic estimates.

        `acs_endpoint` is the ACS 5-year endpoint range like "2018-22".
        Returns a DataFrame with LEAID + the EDGE demographic variables.
        Unlike CCD files, EDGE is a direct CSV (no zip).
        """
        url = EDGE_DISTRICT_DEMOGRAPHICS_URL.format(acs_endpoint=acs_endpoint)
        cache_name = f"edge_district_{acs_endpoint}"
        csv_path = self.cache_dir / f"{cache_name}.csv"
        if not csv_path.exists():
            logger.info("Downloading EDGE district demographics: %s", url)
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            csv_path.write_bytes(resp.content)
        return pd.read_csv(
            csv_path,
            dtype={"LEAID": str, "STATEFP": str, "STATEFIPS": str},
            low_memory=False,
        )
