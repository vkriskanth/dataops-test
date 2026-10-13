"""Example pipeline: raw CSV -> cleaned, aggregated parquet."""

import argparse

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from common import config
from common.spark import get_spark
from common.transforms import snake_case_columns, with_ingest_ts


def transform(df: DataFrame) -> DataFrame:
    return (
        df.transform(snake_case_columns)
        .dropna(subset=["category"])
        .groupBy("category")
        .agg(F.count("*").alias("n"), F.sum("amount").alias("total_amount"))
        .transform(with_ingest_ts)
    )


def run(spark: SparkSession, src: str, dst: str) -> None:
    df = spark.read.option("header", True).option("inferSchema", True).csv(src)
    transform(df).write.mode("overwrite").parquet(dst)


def main() -> None:
    cfg = config.load()
    p = argparse.ArgumentParser()
    p.add_argument("--src", default=cfg.source("raw/example.csv"))
    p.add_argument("--dst", default=cfg.output("processed/example_agg"))
    args = p.parse_args()
    run(get_spark("example_etl", master=cfg.master), args.src, args.dst)


if __name__ == "__main__":
    main()
