"""
Delta Lake + Spark session configuration for socialwarehouse.

Manages SparkSession lifecycle with Delta Lake extensions, S3/HDFS
storage backends, and Sedona spatial extensions.

Usage:
    from socialwarehouse.delta.config import get_spark_session

    spark = get_spark_session()
    df = spark.read.format("delta").load("s3a://warehouse/geo/addresses")
"""

import logging
import os

logger = logging.getLogger("socialwarehouse.delta")

# Storage defaults — override via environment
WAREHOUSE_ROOT = os.environ.get("SW_WAREHOUSE_ROOT", "s3a://socialwarehouse")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://10.10.0.10:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")


def _validate_s3_credentials():
    """Fail-fast at module-load when WAREHOUSE_ROOT requires S3 credentials.

    Pre-D5/SW#127: empty S3_ACCESS_KEY / S3_SECRET_KEY were silently passed
    through to Spark's hadoop config; first read/write surfaced as an
    opaque AWS SDK error mid-query (often hours into a job). Now: if the
    warehouse root looks like s3a:// AND credentials are empty, raise a
    clear RuntimeError at import time naming the env vars to set.

    Carve-out: a non-s3a:// warehouse root (e.g. local file:// for dev)
    does not require S3 creds; validation is skipped.
    """
    if not WAREHOUSE_ROOT.startswith(("s3a://", "s3://", "s3n://")):
        return  # local filesystem or other; no S3 creds needed
    missing = []
    if not S3_ACCESS_KEY:
        missing.append("S3_ACCESS_KEY")
    if not S3_SECRET_KEY:
        missing.append("S3_SECRET_KEY")
    if missing:
        raise RuntimeError(
            f"WAREHOUSE_ROOT={WAREHOUSE_ROOT!r} requires S3 credentials but "
            f"{', '.join(missing)} env var(s) are unset. Set them in the "
            f"environment or point SW_WAREHOUSE_ROOT at a non-S3 path "
            f"(e.g. 'file:///tmp/sw-warehouse' for local dev). (D5 / SW#127)"
        )


_validate_s3_credentials()


def get_spark_session(app_name="socialwarehouse", enable_sedona=False):
    """Get or create a SparkSession configured for Delta Lake.

    Idempotent via Spark's own `SparkSession.builder.getOrCreate()` — that
    is the canonical singleton mechanism for a given JVM. An additional
    @lru_cache layer would be wrong here: a parameterized function with a
    cache_key based on (app_name, enable_sedona) evicts prior cached
    sessions WITHOUT calling .stop() when called with different arg
    combinations, leaking JVM-side state (SparkContext, scheduler, UI
    server). The @lru_cache decorator was removed in fix for SW#126 (D4).

    Args:
        app_name: Spark application name. NOTE: only the FIRST call's
            app_name takes effect for the JVM session; subsequent calls
            return the existing session regardless of app_name. This is
            standard Spark behavior, not a bug.
        enable_sedona: If True, register Apache Sedona UDTs and UDFs for
            spatial operations within Spark. If the session already
            exists without Sedona, this call DOES register Sedona on the
            existing session (registration is idempotent).

    Returns:
        SparkSession with Delta Lake extensions.
    """
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        # S3 configuration
        .config("spark.hadoop.fs.s3a.endpoint", S3_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", S3_ACCESS_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", S3_SECRET_KEY)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        # Delta defaults
        .config("spark.databricks.delta.schema.autoMerge.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "zstd")
    )

    if enable_sedona:
        builder = (
            builder
            .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
            .config("spark.kryo.registrator", "org.apache.sedona.core.serde.SedonaKryoRegistrator")
        )

    spark = builder.getOrCreate()

    if enable_sedona:
        try:
            from sedona.register import SedonaRegistrator
            SedonaRegistrator.registerAll(spark)
            logger.info("Sedona spatial extensions registered")
        except ImportError:
            logger.warning("apache-sedona not installed, spatial UDFs unavailable")

    logger.info("SparkSession created: %s (Delta Lake enabled)", app_name)
    return spark


def get_table_path(tier, table_name):
    """Build a Delta table path.

    Args:
        tier: Storage tier — 'bronze', 'silver', or 'gold'.
        table_name: Table name within the tier.

    Returns:
        Full path like 's3a://socialwarehouse/silver/addresses'.
    """
    return f"{WAREHOUSE_ROOT}/{tier}/{table_name}"
