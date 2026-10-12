"""Shared SparkSession factory so every pipeline is configured consistently."""

from pyspark.sql import SparkSession


def get_spark(app_name: str = "dataops", master: str = "local[*]", **conf: str) -> SparkSession:
    builder = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.showConsoleProgress", "false")
    )
    for key, value in conf.items():
        builder = builder.config(key.replace("__", "."), value)
    return builder.getOrCreate()
