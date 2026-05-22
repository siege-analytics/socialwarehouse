"""Source registry for scripts/fetch.py.

Adding a new source:
  1. Subclass ``Source`` in a new module under scripts/sources/.
  2. Add its class to the ``SOURCES`` mapping below.
  3. Document the new payload shape in the module docstring.
  4. No changes to scripts/fetch.py needed — dispatch is via this map.
"""

from __future__ import annotations

from .acs import ACSSource
from .base import Source
from .census_tiger import CensusTigerSource
from .rdh import RDHSource

SOURCES: dict[str, type[Source]] = {
    ACSSource.name: ACSSource,
    CensusTigerSource.name: CensusTigerSource,
    RDHSource.name: RDHSource,
}

__all__ = [
    "SOURCES",
    "Source",
    "ACSSource",
    "CensusTigerSource",
    "RDHSource",
]
