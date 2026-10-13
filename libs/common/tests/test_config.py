from common.config import EnvConfig, load


def cfg(**overrides: object) -> EnvConfig:
    base = {
        "name": "dev",
        "base_path": "s3://bucket/dataops",
        "namespace": "",
        "master": "local[*]",
        "features": frozenset(),
    }
    return EnvConfig(**{**base, **overrides})  # type: ignore[arg-type]


def test_source_is_never_namespaced():
    c = cfg(namespace="pr42")
    assert c.source("raw/example.csv") == "s3://bucket/dataops/raw/example.csv"


def test_output_is_namespaced_when_a_namespace_is_set():
    c = cfg(namespace="pr42")
    assert c.output("processed/agg") == "s3://bucket/dataops/pr42/processed/agg"


def test_output_is_plain_without_a_namespace():
    assert cfg().output("processed/agg") == "s3://bucket/dataops/processed/agg"


def test_uri_scheme_survives_joining():
    assert cfg(base_path="s3://bucket/").output("a", "b") == "s3://bucket/a/b"


def test_feature_flags():
    c = cfg(features=frozenset({"agg_v2"}))
    assert c.enabled("agg_v2")
    assert not c.enabled("agg_v3")


def test_load_defaults_to_local(monkeypatch):
    for var in ("DATAOPS_ENV", "DATAOPS_BASE_PATH", "DATA_DIR", "DATAOPS_NAMESPACE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("DATAOPS_FEATURES", raising=False)
    c = load()
    assert c.name == "local"
    assert c.base_path == "data"
    assert c.namespace == ""


def test_load_reads_the_environment(monkeypatch):
    monkeypatch.setenv("DATAOPS_ENV", "qat")
    monkeypatch.setenv("DATAOPS_BASE_PATH", "s3://qat/dataops")
    monkeypatch.setenv("DATAOPS_NAMESPACE", "")
    monkeypatch.setenv("DATAOPS_FEATURES", "agg_v2, dedupe ")
    c = load()
    assert c.name == "qat"
    assert c.base_path == "s3://qat/dataops"
    assert c.features == frozenset({"agg_v2", "dedupe"})
