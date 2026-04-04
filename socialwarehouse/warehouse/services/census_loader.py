"""
Load Census ACS and Decennial data into warehouse fact tables.

Uses siege_utilities Census API client for data retrieval. Populates
FactACSEstimate and FactDecennialCount with proper dimension linkage.
"""

import logging

from django.db import transaction

logger = logging.getLogger("socialwarehouse.warehouse")

# Standard ACS variable groups for loading
ACS_VARIABLE_GROUPS = {
    "population": ["B01001_001E"],
    "race": [
        "B02001_002E", "B02001_003E", "B02001_004E", "B02001_005E",
        "B02001_006E", "B02001_007E", "B02001_008E",
    ],
    "hispanic": ["B03003_003E"],
    "income": ["B19013_001E"],
    "poverty": ["B17001_002E"],
    "housing": ["B25001_001E", "B25002_002E", "B25002_003E"],
    "education": ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"],
}


class CensusLoaderService:
    """Load Census data into the warehouse star schema."""

    def __init__(self, census_api_key: str | None = None):
        self.api_key = census_api_key

    def load_acs_estimates(
        self,
        vintage_year: int = 2022,
        summary_level: str = "tract",
        state_fips: str | None = None,
        variable_groups: list[str] | None = None,
    ) -> int:
        """Load ACS 5-year estimates into FactACSEstimate.

        Fetches data from Census API, creates DimCensusVariable records if needed,
        links to DimGeography, and inserts fact rows.

        Returns count of fact rows created.
        """
        from siege_utilities.census import CensusAPIClient
        from socialwarehouse.warehouse.models import (
            DimGeography, DimSurvey, DimCensusVariable, FactACSEstimate,
        )

        # Resolve variable list
        if variable_groups is None:
            variable_groups = list(ACS_VARIABLE_GROUPS.keys())

        variables = []
        for group in variable_groups:
            if group in ACS_VARIABLE_GROUPS:
                variables.extend(ACS_VARIABLE_GROUPS[group])
            else:
                variables.append(group)

        # Get or create the survey dimension
        survey, _ = DimSurvey.objects.get_or_create(
            survey_type="acs5",
            vintage_year=vintage_year,
            defaults={"name": f"ACS 5-Year {vintage_year}"},
        )

        # Fetch from Census API
        client = CensusAPIClient(api_key=self.api_key)
        logger.info(
            "Fetching ACS %d, %s level, %d variables%s",
            vintage_year, summary_level, len(variables),
            f" (state {state_fips})" if state_fips else "",
        )

        try:
            data = client.fetch(
                dataset="acs5",
                year=vintage_year,
                variables=variables,
                geography=summary_level,
                state=state_fips,
            )
        except Exception as e:
            logger.error("Census API fetch failed: %s", e)
            return 0

        if not data:
            logger.warning("No data returned from Census API")
            return 0

        # Ensure variable dimensions exist
        var_dims = {}
        for var_code in variables:
            dim, _ = DimCensusVariable.objects.get_or_create(
                variable_code=var_code,
                dataset="acs5",
                defaults={"name": var_code, "universe": ""},
            )
            var_dims[var_code] = dim

        # Load fact rows
        count = 0
        for row in data:
            geoid = row.get("GEO_ID", row.get("geoid", ""))
            if not geoid:
                continue

            # Clean GEOID (Census API sometimes prefixes with summary level)
            if "|" in geoid:
                geoid = geoid.split("|")[-1]

            # Find geography dimension
            geo_dim = DimGeography.objects.filter(
                geoid=geoid, vintage_year=vintage_year
            ).first()

            if not geo_dim:
                continue

            for var_code in variables:
                value = row.get(var_code)
                moe_value = row.get(var_code.replace("E", "M"))

                if value is None or value in ("-", "null", "**"):
                    continue

                try:
                    estimate = float(value)
                    moe = float(moe_value) if moe_value and moe_value not in ("-", "null", "**") else None
                except (ValueError, TypeError):
                    continue

                # Calculate coefficient of variation
                cv = None
                if moe and estimate != 0:
                    se = moe / 1.645
                    cv = abs(se / estimate) * 100

                # Reliability rating
                reliability = "high"
                if cv and cv > 40:
                    reliability = "low"
                elif cv and cv > 20:
                    reliability = "medium"

                FactACSEstimate.objects.update_or_create(
                    geography=geo_dim,
                    variable=var_dims[var_code],
                    survey=survey,
                    defaults={
                        "estimate": estimate,
                        "margin_of_error": moe,
                        "coefficient_of_variation": cv,
                        "reliability": reliability,
                    },
                )
                count += 1

        logger.info("Loaded %d ACS fact rows for %d/%s", count, vintage_year, summary_level)
        return count

    def load_decennial_counts(
        self,
        census_year: int = 2020,
        summary_level: str = "tract",
        state_fips: str | None = None,
    ) -> int:
        """Load Decennial Census counts into FactDecennialCount.

        Returns count of fact rows created.
        """
        from siege_utilities.census import CensusAPIClient
        from socialwarehouse.warehouse.models import (
            DimGeography, DimSurvey, DimCensusVariable, FactDecennialCount,
        )

        # PL 94-171 variables
        variables = [
            "P1_001N",   # Total population
            "P1_003N",   # White alone
            "P1_004N",   # Black alone
            "P2_002N",   # Hispanic
        ]

        survey, _ = DimSurvey.objects.get_or_create(
            survey_type="dec_pl",
            vintage_year=census_year,
            defaults={"name": f"PL 94-171 {census_year}"},
        )

        client = CensusAPIClient(api_key=self.api_key)
        logger.info("Fetching Decennial %d PL data, %s level", census_year, summary_level)

        try:
            data = client.fetch(
                dataset="dec/pl",
                year=census_year,
                variables=variables,
                geography=summary_level,
                state=state_fips,
            )
        except Exception as e:
            logger.error("Census API fetch failed: %s", e)
            return 0

        if not data:
            return 0

        var_dims = {}
        for var_code in variables:
            dim, _ = DimCensusVariable.objects.get_or_create(
                variable_code=var_code,
                dataset="dec_pl",
                defaults={"name": var_code},
            )
            var_dims[var_code] = dim

        count = 0
        for row in data:
            geoid = row.get("GEO_ID", row.get("geoid", ""))
            if "|" in geoid:
                geoid = geoid.split("|")[-1]
            if not geoid:
                continue

            geo_dim = DimGeography.objects.filter(
                geoid=geoid, vintage_year=census_year
            ).first()
            if not geo_dim:
                continue

            for var_code in variables:
                value = row.get(var_code)
                if value is None or value in ("-", "null"):
                    continue
                try:
                    count_val = int(value)
                except (ValueError, TypeError):
                    continue

                FactDecennialCount.objects.update_or_create(
                    geography=geo_dim,
                    variable=var_dims[var_code],
                    survey=survey,
                    defaults={"count": count_val},
                )
                count += 1

        logger.info("Loaded %d decennial fact rows for %d/%s", count, census_year, summary_level)
        return count
