"""
Social Warehouse configuration via Pydantic settings.

Replaces the old code/python/settings.py which had:
- Hardcoded Texas state list
- Manual TIGER URLs with outdated congress numbers (cd116)
- Plaintext credentials
- Commented-out state lists
- `from settings import *` pattern

Now: all configuration comes from environment variables (loaded from .env).
State FIPS lookups come from siege_utilities instead of hand-maintained dicts.

Example usage:
    from swh.config import settings

    # Access database connection string
    print(settings.database.connection_string)

    # Access Census year
    print(settings.census.year)

    # Get states to process
    states = settings.census.get_state_fips_list()
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class DatabaseSettings(BaseSettings):
    """PostGIS connection settings, populated from POSTGRES_* env vars."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env")

    host: str = "postgis"
    port: int = 5432
    db: str = "gis"
    user: str = "socialwarehouse"
    password: str = "CHANGEME"

    @property
    def connection_string(self) -> str:
        """SQLAlchemy connection string for PostGIS.

        Uses SQLAlchemy's URL.create() to safely handle reserved characters
        (@, :, /, etc.) in credentials.

        Example:
            >>> settings.database.connection_string
            'postgresql://socialwarehouse:CHANGEME@postgis:5432/gis'
        """
        return str(URL.create(
            drivername="postgresql",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.db,
        ))

    @property
    def psycopg2_dsn(self) -> str:
        """DSN string for psycopg2.connect().

        Uses keyword=value format which handles special characters natively.

        Example:
            >>> settings.database.psycopg2_dsn
            'host=postgis port=5432 dbname=gis user=socialwarehouse password=CHANGEME'
        """
        return f"host={self.host} port={self.port} dbname={self.db} user={self.user} password={self.password}"


class CensusSettings(BaseSettings):
    """Census data download settings, populated from CENSUS_* env vars."""

    model_config = SettingsConfigDict(env_prefix="CENSUS_", env_file=".env")

    year: int = 2023
    congress_number: int = 118
    states: str = "all"
    target_crs: int = 4269
    boundary_types: list[str] = Field(
        default=["tabblock20", "sldu", "sldl", "cd", "county", "state"]
    )

    def get_state_fips_list(self) -> list[str]:
        """Return a list of state FIPS codes to process.

        If CENSUS_STATES=all, returns all 50 states + DC via siege_utilities.
        Otherwise, parses a comma-separated list of FIPS codes.

        Example:
            >>> settings = CensusSettings(states="48,06,36")
            >>> settings.get_state_fips_list()
            ['48', '06', '36']

            >>> settings = CensusSettings(states="all")
            >>> len(settings.get_state_fips_list())
            51
        """
        if self.states.lower() == "all":
            from siege_utilities.states import STATEFIPS_LOOKUP_DICT

            return list(STATEFIPS_LOOKUP_DICT.keys())
        return [s.strip().zfill(2) for s in self.states.split(",")]


class SparkSettings(BaseSettings):
    """PySpark session settings, populated from SPARK_* env vars.

    Defaults target local development (``local[*]``). The Docker
    ``make up-spark`` profile injects a cluster master URL via
    ``SPARK_MASTER``.
    """

    model_config = SettingsConfigDict(env_prefix="SPARK_", env_file=".env", extra="ignore")

    app_name: str = "socialwarehouse"
    master: str = "local[*]"
    driver_memory: str = "2g"
    executor_memory: str = "2g"

    def build_session(self):
        """Build a configured ``SparkSession`` with the project's defaults.

        Imports ``pyspark`` lazily so the rest of the project can read
        ``settings`` without requiring PySpark to be installed.
        """
        from pyspark.sql import SparkSession

        return (
            SparkSession.builder
            .appName(self.app_name)
            .master(self.master)
            .config("spark.driver.memory", self.driver_memory)
            .config("spark.executor.memory", self.executor_memory)
            .getOrCreate()
        )


class FECSettings(BaseSettings):
    """FEC campaign-finance analysis paths, populated from FEC_* env vars.

    Defaults target the cyberpower deployment (``/mnt/data/electinfo``).
    Laptop / per-developer overrides come from env vars, not from a
    ``WORKING_ON_LAPTOP`` boolean.
    """

    model_config = SettingsConfigDict(env_prefix="FEC_", env_file=".env", extra="ignore")

    base_path: str = "/mnt/data/electinfo"
    bulk_subdir: str = "bulk"
    graph_subdir: str = "graph"

    @property
    def bulk_path(self) -> str:
        """Directory containing FEC bulk-data CSVs (per-cycle subdirs)."""
        return f"{self.base_path}/{self.bulk_subdir}"

    @property
    def graph_path(self) -> str:
        """Directory where the campaign-finance graph parquet lives.

        ``build_graph`` writes vertices + edges parquet here;
        ``committee_centrality`` reads from the same location. Pre-
        modernization, build_graph wrote to ``bulk/exports`` while
        centrality read from ``graph/`` — they couldn't run end-to-end
        without a manual file move. This setting collapses both onto a
        single canonical path.
        """
        return f"{self.base_path}/{self.graph_subdir}"


class SocialWarehouseSettings(BaseSettings):
    """Top-level settings container.

    Example:
        >>> from swh.config import settings
        >>> settings.database.host
        'postgis'
        >>> settings.census.year
        2023
    """

    model_config = SettingsConfigDict(env_file=".env")

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    census: CensusSettings = Field(default_factory=CensusSettings)
    spark: SparkSettings = Field(default_factory=SparkSettings)
    fec: FECSettings = Field(default_factory=FECSettings)


# Module-level singleton — import this in other modules.
settings = SocialWarehouseSettings()
