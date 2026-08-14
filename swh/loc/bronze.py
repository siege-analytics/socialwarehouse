"""Fetch the unitedstates/congress-legislators bulk dataset (LoC-family).

Thin I/O layer kept out of `materialize` so the mappers + materializer
stay testable with in-memory records. The dataset is public-domain JSON,
~13k records across current + historical.
"""

from __future__ import annotations

import json
import urllib.request

CURRENT_URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
HISTORICAL_URL = "https://unitedstates.github.io/congress-legislators/legislators-historical.json"


def fetch_json(url: str, timeout: int = 60) -> list:
    """GET a congress-legislators JSON bulk file and return the parsed list."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted public dataset)
        return json.loads(resp.read().decode("utf-8"))


def fetch_legislators(include_historical: bool = True) -> list:
    """Return current (and optionally historical) legislator records."""
    records = fetch_json(CURRENT_URL)
    if include_historical:
        records = records + fetch_json(HISTORICAL_URL)
    return records
