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
from functools import lru_cache

logger = logging.getLogger("socialwarehouse.delta")

# Storage defaults — override via environment
WAREHOUSE_ROOT = os.environ.get("SW_WAREHOUSE_ROOT", "s3a://socialwarehouse")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://10.10.0.10:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")


@lru_cache(maxsize=1)
def get_spark_session(app_name="socialwarehouse", enable_sedona=False):
    """Get or create a SparkSession configured for Delta Lake.

    Args:
        app_name: Spark application name.
        enable_sedona: If True, register Apache Sedona UDTs and UDFs for
            spatial operations within Spark.

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
