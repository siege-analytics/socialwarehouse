"""IRS SOI ZIP-code aggregates downloader.

Files-only path (no API key). The IRS publishes per-state CSV/XLSX
files under irs.gov/statistics/soi-tax-stats-individual-income-tax-
statistics-zip-code-data-soi each tax year.

TODO(SU#535): lift this to siege_utilities (mirrors SU#533 / #534 for
BLS QCEW / NCES). Kept SW-local until SU lands an IRS SOI helper.
"""

import io
import logging

import pandas as pd
import requests


logger = logging.getLogger(__name__)


# Base URL pattern; the IRS occasionally re-publishes under
# slightly different paths, so callers can override via __init__.
DEFAULT_BASE_URL = "https://www.irs.gov/pub/irs-soi"


class IRSSOIFiles:
    """Thin wrapper around requests + pandas for SOI ZIP files."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, session=None):
        self.base_url = base_url
        self.session = session or requests.Session()

    def url_for(self, tax_year: int, state_abbrev: str) -> str:
        # e.g. 2022 -> /22zpallnoagi.csv (national, all AGI) — varies.
        # Per-state: /22zp06ca.csv style. Convention varies year over year;
        # callers can override `url_for` if a release deviates.
        yy = f"{tax_year % 100:02d}"
        return f"{self.base_url}/{yy}zp{state_abbrev.lower()}.csv"

    def load(self, *, tax_year: int, state_abbrev: str) -> pd.DataFrame:
        """Download + parse a single per-state SOI release.

        Returns a DataFrame with the IRS column names intact
        (zipcode, agi_stub, N1, N2, A00100, A04800, A06500, ...).
        Caller is responsible for re-keying to ZCTA conventions.
        """
        url = self.url_for(tax_year, state_abbrev)
        logger.info("Fetching IRS SOI: %s", url)
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        return pd.read_csv(io.BytesIO(resp.content), low_memory=False)
