"""Base class for data sources fetched by scripts/fetch.py.

Each source implements check / fetch / load / update_state lifecycle
methods plus optional ``add_arguments`` for source-specific CLI args.

The ``payload`` returned by ``check`` is opaque to the orchestrator —
each source defines its own shape (e.g. an int vintage year for
vintage-based sources, a list of dicts for catalog-based sources).
``fetch``, ``load``, ``update_state``, and ``describe_payload``
receive the same payload back.

Adding a new source: subclass ``Source``, set ``name`` /
``description`` / ``default_state_file``, implement the abstract
methods, and register the class in ``scripts/sources/__init__.py``'s
``SOURCES`` mapping.
"""

from __future__ import annotations

import argparse
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Source(ABC):
    """Lifecycle: check -> fetch -> load -> update_state."""

    name: str = ""
    description: str = ""
    default_state_file: Path = Path("/tmp/fetch-state.txt")

    def __init__(self, state_file: Path | None = None):
        self.state_file = state_file or self.default_state_file

    @abstractmethod
    def check(self) -> tuple[bool, Any]:
        """Query the source.

        Returns ``(has_update, payload)``. ``has_update`` is True when there
        is new work to do; ``payload`` is the source-specific description
        of what work (typically an int vintage year or a list of catalog
        entries). When ``has_update`` is False, ``payload`` may be None or
        an empty container."""

    @abstractmethod
    def fetch(self, payload: Any, args: argparse.Namespace) -> None:
        """Pull the data for ``payload``. Side-effect: writes to disk
        (or no-op if the source's load() is itself the fetcher, e.g. for
        API-driven loads)."""

    @abstractmethod
    def load(self, payload: Any, args: argparse.Namespace) -> None:
        """Trigger the DB load for ``payload``. Typically subprocesses
        a manage.py command."""

    @abstractmethod
    def update_state(self, payload: Any) -> None:
        """Record that ``payload`` was successfully loaded.

        The state-file format is subclass-defined: vintage-based sources
        typically write a single int; catalog-based sources typically
        write a JSON record of known IDs."""

    @abstractmethod
    def describe_payload(self, payload: Any) -> str:
        """One-line human description of ``payload`` for log and check-only
        output. Subclasses should return something like
        ``"ACS 2023"`` or ``"5 new plans"``."""

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Add source-specific args to the parser. Subclasses override.

        Common args (state-file, manage-py, verbose, check-only, dry-run)
        are added by scripts/fetch.py before this hook is invoked.
        Subclasses should only add args unique to their source, and the
        argument names should not clash with the common set."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
