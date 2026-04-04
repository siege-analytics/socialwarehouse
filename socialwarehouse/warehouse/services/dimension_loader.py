"""
Load warehouse dimensions from siege_utilities boundary models.

DimGeography: SCD Type 2 from siege_geo boundary models (State, County, Tract, etc.)
DimTime: Pre-populated calendar table with Census/election flags
DimRedistrictingCycle: From RedistrictingPlan records
DimSurvey: From Census API dataset discovery
"""

import logging
from datetime import date, timedelta

from django.db import transaction

logger = logging.getLogger("socialwarehouse.warehouse")


class DimensionLoaderService:
    """Load and maintain warehouse dimension tables."""

    def load_geography_from_siege(self, vintage_year: int = 2020,
                                  summary_levels: list[str] | None = None) -> int:
        """Load DimGeography records from siege_utilities boundary models.

        Implements SCD Type 2: each (geoid, vintage_year) combination gets
        one row. Parent FK is set for drill-up (tract → county → state).

        Returns count of records created/updated.
        """
        from siege_utilities.geo.django.models import (
            State, County, Tract, BlockGroup, Place,
            CongressionalDistrict, StateLegislativeLower, StateLegislativeUpper,
        )
        from socialwarehouse.warehouse.models import DimGeography

        if summary_levels is None:
            summary_levels = ["state", "county", "tract", "blockgroup", "place", "cd", "sldl", "sldu"]

        MODEL_MAP = {
            "state": (State, None),
            "county": (County, "state"),
            "tract": (Tract, "county"),
            "blockgroup": (BlockGroup, "tract"),
            "place": (Place, "state"),
            "cd": (CongressionalDistrict, "state"),
            "sldl": (StateLegislativeLower, "state"),
            "sldu": (StateLegislativeUpper, "state"),
        }

        total = 0

        for level in summary_levels:
            if level not in MODEL_MAP:
                logger.warning("Unknown summary level: %s", level)
                continue

            model_class, parent_level = MODEL_MAP[level]
            boundaries = model_class.objects.filter(vintage_year=vintage_year)
            count = 0

            for boundary in boundaries.iterator():
                # Build parent lookup
                parent = None
                if parent_level:
                    parent_geoid = self._derive_parent_geoid(boundary.geoid, parent_level)
                    if parent_geoid:
                        parent = DimGeography.objects.filter(
                            geoid=parent_geoid, vintage_year=vintage_year
                        ).first()

                dim, created = DimGeography.objects.update_or_create(
                    geoid=boundary.geoid,
                    vintage_year=vintage_year,
                    defaults={
                        "name": boundary.name,
                        "summary_level": level,
                        "state_fips": boundary.state_fips,
                        "geometry": boundary.geometry if hasattr(boundary, "geometry") else None,
                        "area_land": getattr(boundary, "area_land", None),
                        "area_water": getattr(boundary, "area_water", None),
                        "internal_point": getattr(boundary, "internal_point", None),
                        "parent": parent,
                        "is_current": True,
                    },
                )
                count += 1

            logger.info("Loaded %d %s records for vintage %d", count, level, vintage_year)
            total += count

        return total

    def load_time_dimension(self, start_year: int = 2000, end_year: int = 2030) -> int:
        """Pre-populate DimTime with calendar dates and Census/election flags."""
        from socialwarehouse.warehouse.models import DimTime

        start = date(start_year, 1, 1)
        end = date(end_year, 12, 31)
        current = start
        count = 0

        while current <= end:
            # Election flags
            is_election_day = (
                current.month == 11
                and current.weekday() == 1  # Tuesday
                and 2 <= current.day <= 8   # First Tuesday after first Monday
            )
            is_presidential = is_election_day and current.year % 4 == 0
            is_midterm = is_election_day and current.year % 4 == 2

            # Census flags
            is_census_day = current == date(current.year, 4, 1) and current.year % 10 == 0

            # Fiscal year
            federal_fiscal_year = current.year if current.month >= 10 else current.year - 1

            DimTime.objects.update_or_create(
                calendar_date=current,
                defaults={
                    "year": current.year,
                    "quarter": (current.month - 1) // 3 + 1,
                    "month": current.month,
                    "day_of_month": current.day,
                    "day_of_week": current.weekday(),
                    "week_of_year": current.isocalendar()[1],
                    "is_election_day": is_election_day,
                    "is_presidential_election": is_presidential,
                    "is_midterm_election": is_midterm,
                    "is_census_day": is_census_day,
                    "federal_fiscal_year": federal_fiscal_year,
                },
            )
            count += 1
            current += timedelta(days=1)

        logger.info("Loaded %d dates for DimTime (%d-%d)", count, start_year, end_year)
        return count

    def load_redistricting_cycles(self) -> int:
        """Load DimRedistrictingCycle from RedistrictingPlan records."""
        from siege_utilities.geo.django.models import RedistrictingPlan
        from socialwarehouse.warehouse.models import DimRedistrictingCycle

        cycles = (
            RedistrictingPlan.objects
            .values_list("cycle_year", flat=True)
            .distinct()
            .order_by("cycle_year")
        )

        count = 0
        for cycle_year in cycles:
            DimRedistrictingCycle.objects.update_or_create(
                cycle_year=cycle_year,
                defaults={
                    "census_year": cycle_year,
                    "effective_start": date(cycle_year + 2, 1, 1),
                    "effective_end": date(cycle_year + 12, 1, 1),
                },
            )
            count += 1

        logger.info("Loaded %d redistricting cycles", count)
        return count

    def _derive_parent_geoid(self, geoid: str, parent_level: str) -> str | None:
        """Derive parent GEOID from child GEOID using FIPS structure."""
        PARENT_LENGTHS = {
            "state": 2,     # XX
            "county": 5,    # XXYYY
            "tract": 11,    # XXYYYZZZZZZ
        }
        length = PARENT_LENGTHS.get(parent_level)
        if length and len(geoid) >= length:
            return geoid[:length]
        return None
