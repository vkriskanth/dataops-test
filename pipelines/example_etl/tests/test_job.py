from example_etl.job import transform


def test_transform_aggregates(spark):
    df = spark.createDataFrame(
        [("a", 1.0), ("a", 2.0), ("b", 5.0), (None, 9.0)], ["Category", "Amount"]
    )
    rows = {r["category"]: (r["n"], r["total_amount"]) for r in transform(df).collect()}
    assert rows == {"a": (2, 3.0), "b": (1, 5.0)}
