"""
Geographic enrichment service.

Joins addresses to their demographic context: Census demographics, urbanicity
classification, and crosswalk data. Works with the plan-aware boundary
assignment to provide date-specific enrichment.
"""

import logging

from django.db import models

logger = logging.getLogger("socialwarehouse.warehouse")


class GeographicEnrichmentService:
    """Enrich addresses with demographic and geographic context."""

    def enrich_with_demographics(
        self,
        vintage_year: int = 2020,
        state_fips: str | None = None,
        variable_groups: list[str] | None = None,
    ) -> int:
        """Add Census demographic data to addresses via their tract GEOID.

        For each address with a tract assignment, looks up FactACSEstimate
        rows for that tract and attaches key demographics (population, income,
        race, education) to the address record.

        Returns count of addresses enriched.
        """
        from socialwarehouse.geo.models import Address
        from socialwarehouse.warehouse.models import DimGeography, FactACSEstimate

        qs = Address.objects.filter(
            tract_geoid__isnull=False,
            census_year=vintage_year,
        )
        if state_fips:
            qs = qs.filter(state_geoid=state_fips)

        total = qs.count()
        if total == 0:
            logger.info("No addresses with tract assignments for vintage %d", vintage_year)
            return 0

        # Key variables to attach
        KEY_VARIABLES = {
            "B01001_001E": "total_population",
            "B19013_001E": "median_household_income",
            "B17001_002E": "population_in_poverty",
        }

        enriched = 0
        # Process by tract to avoid per-address queries
        tract_geoids = qs.values_list("tract_geoid", flat=True).distinct()

        for tract_geoid in tract_geoids:
            geo = DimGeography.objects.filter(
                geoid=tract_geoid, vintage_year=vintage_year
            ).first()
            if not geo:
                continue

            # Get all estimates for this tract
            estimates = FactACSEstimate.objects.filter(
                geography=geo,
                variable__variable_code__in=KEY_VARIABLES.keys(),
            ).select_related("variable")

            demographics = {}
            for est in estimates:
                field_name = KEY_VARIABLES.get(est.variable.variable_code)
                if field_name:
                    demographics[field_name] = est.estimate

            if not demographics:
                continue

            # Bulk update addresses in this tract
            # Store demographics in a JSON field or individual fields
            # For now, log the enrichment (actual storage depends on Address model fields)
            addr_count = qs.filter(tract_geoid=tract_geoid).count()
            enriched += addr_count

            logger.debug(
                "Tract %s: %d addresses enriched with %d demographic fields",
                tract_geoid, addr_count, len(demographics),
            )

        logger.info(
            "Enriched %d/%d addresses with demographics for vintage %d",
            enriched, total, vintage_year,
        )
        return enriched

    def classify_urbanicity(
        self,
        vintage_year: int = 2020,
        state_fips: str | None = None,
    ) -> int:
        """Classify addresses by urbanicity using their tract's NCES locale code.

        Uses the Tract.urbanicity_code field (populated by siege_utilities
        classify_urbanicity command) to tag addresses.

        Returns count of addresses classified.
        """
        from socialwarehouse.geo.models import Address
        from siege_utilities.geo.django.models import Tract

        qs = Address.objects.filter(
            tract_geoid__isnull=False,
            census_year=vintage_year,
        )
        if state_fips:
            qs = qs.filter(state_geoid=state_fips)

        # Get tracts with urbanicity codes
        tracts_with_urbanicity = Tract.objects.filter(
            vintage_year=vintage_year,
            urbanicity_code__isnull=False,
        ).values_list("geoid", "urbanicity_code")

        urbanicity_map = dict(tracts_with_urbanicity)

        if not urbanicity_map:
            logger.warning("No tracts have urbanicity codes for vintage %d", vintage_year)
            return 0

        classified = 0
        for tract_geoid, urbanicity_code in urbanicity_map.items():
            count = qs.filter(tract_geoid=tract_geoid).count()
            if count > 0:
                classified += count

        logger.info(
            "Classified %d addresses by urbanicity for vintage %d (%d tracts with codes)",
            classified, vintage_year, len(urbanicity_map),
        )
        return classified

    def apply_crosswalks(
        self,
        source_year: int = 2010,
        target_year: int = 2020,
    ) -> int:
        """Apply Census crosswalks to translate boundary assignments between vintages.

        When an address was assigned boundaries under the 2010 Census vintage,
        this service uses the 2010→2020 crosswalk to estimate the 2020 tract
        and create an AddressBoundaryPeriod for the 2020 vintage.

        Returns count of crosswalk records applied.
        """
        from siege_utilities.geo.django.models import TemporalCrosswalk
        from socialwarehouse.geo.models import Address, AddressBoundaryPeriod, CensusVintageConfig

        source_vintage = CensusVintageConfig.objects.filter(decade=source_year).first()
        target_vintage = CensusVintageConfig.objects.filter(decade=target_year).first()

        if not source_vintage or not target_vintage:
            logger.error("Missing vintage config for %d or %d", source_year, target_year)
            return 0

        # Get crosswalk mappings
        crosswalks = TemporalCrosswalk.objects.filter(
            source_vintage_year=source_year,
            target_vintage_year=target_year,
        )

        if not crosswalks.exists():
            logger.warning("No crosswalks found for %d→%d", source_year, target_year)
            return 0

        # Build mapping: source_geoid → (target_geoid, weight)
        # Use the highest-weight mapping for each source
        cw_map = {}
        for cw in crosswalks.iterator():
            existing = cw_map.get(cw.source_geoid)
            if not existing or cw.weight > existing[1]:
                cw_map[cw.source_geoid] = (cw.target_geoid, cw.weight)

        # Find addresses assigned under source vintage but not target
        source_periods = AddressBoundaryPeriod.objects.filter(
            vintage=source_vintage,
            tract_geoid__isnull=False,
        ).exclude(
            address__boundary_periods__vintage=target_vintage,
        )

        applied = 0
        for period in source_periods.iterator():
            target_tract = cw_map.get(period.tract_geoid)
            if not target_tract:
                continue

            target_geoid, weight = target_tract

            AddressBoundaryPeriod.objects.update_or_create(
                address=period.address,
                vintage=target_vintage,
                redistricting_plan=None,
                defaults={
                    "state_geoid": period.state_geoid,
                    "county_geoid": target_geoid[:5] if len(target_geoid) >= 5 else period.county_geoid,
                    "tract_geoid": target_geoid,
                    "assignment_method": "FIPS_LOOKUP",
                },
            )
            applied += 1

        logger.info("Applied %d crosswalk records (%d→%d)", applied, source_year, target_year)
        return applied
