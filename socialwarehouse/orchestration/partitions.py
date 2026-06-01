"""Partition definitions for Census vintage backfills.

Provides a ``StaticPartitionsDefinition`` listing known ACS and
Decennial vintages, a parser that turns partition keys into typed
named tuples, and a hot/cold tier policy that controls which vintages
materialize to PostGIS.

Cold-tier policy follows ``docs/production-operations.md`` section 5:
historical vintages stay in Delta Lake; only the hot window
materializes to PostGIS.

Usage::

    from socialwarehouse.orchestration.partitions import (
        CENSUS_VINTAGE_PARTITIONS,
        parse_vintage_partition,
        is_hot_vintage,
    )
"""

from __future__ import annotations

from typing import NamedTuple

from dagster import StaticPartitionsDefinition


class VintagePartition(NamedTuple):
    """Parsed vintage partition key."""

    survey_type: str
    vintage_year: int
    end_year: int


_VINTAGE_KEYS = [
    "dec_2020",
    "dec_2010",
    "acs5_2022",
    "acs5_2021",
    "acs5_2019",
    "acs5_2014",
    "acs5_2009",
]

CENSUS_VINTAGE_PARTITIONS = StaticPartitionsDefinition(_VINTAGE_KEYS)


def parse_vintage_partition(partition_key: str) -> VintagePartition:
    """Parse a partition key like ``"acs5_2022"`` into its components.

    Raises:
        ValueError: If the key doesn't match the expected format.
    """
    parts = partition_key.split("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid vintage partition key: {partition_key!r}")

    survey_type, year_str = parts
    if survey_type not in ("acs5", "dec"):
        raise ValueError(
            f"Unknown survey type {survey_type!r} in partition key {partition_key!r}; "
            f"expected 'acs5' or 'dec'"
        )

    try:
        vintage_year = int(year_str)
    except ValueError:
        raise ValueError(f"Non-integer year in partition key: {partition_key!r}")

    return VintagePartition(
        survey_type=survey_type,
        vintage_year=vintage_year,
        end_year=vintage_year,
    )


def is_hot_vintage(vintage_year: int, current_vintage: int, hot_window_count: int = 1) -> bool:
    """Determine whether a vintage falls within the hot window for PostGIS materialization.

    Vintages within the hot window are materialized to PostGIS.
    Vintages outside the window remain in Delta Lake only (cold tier).

    Args:
        vintage_year: The vintage year to check.
        current_vintage: The most recent / current vintage year.
        hot_window_count: Number of recent vintages to keep hot (default 1 = only current).
    """
    if hot_window_count <= 0:
        return False
    return vintage_year > (current_vintage - hot_window_count)


def survey_type_prefix(partition: VintagePartition) -> str:
    """Return the survey_type filter prefix for SILVER_DEMOGRAPHICS rows."""
    if partition.survey_type == "acs5":
        return "acs5"
    return "decennial"
