from common.transforms import snake_case_columns


def test_snake_case_columns(spark):
    df = spark.createDataFrame([(1, 2)], ["First Col", " Second "])
    assert snake_case_columns(df).columns == ["first_col", "second"]
