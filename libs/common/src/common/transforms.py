"""Reusable DataFrame transformations (use with DataFrame.transform)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def snake_case_columns(df: DataFrame) -> DataFrame:
    return df.toDF(*[c.strip().lower().replace(" ", "_") for c in df.columns])


def with_ingest_ts(df: DataFrame, col: str = "_ingested_at") -> DataFrame:
    return df.withColumn(col, F.current_timestamp())
