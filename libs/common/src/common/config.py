"""Per-environment configuration, injected at runtime so one artifact serves every env.

Nothing here is environment-specific at build time: the same wheel runs in dev, qat and
prd, and only these env vars differ. Dev deploys set ``DATAOPS_NAMESPACE`` so every
developer writes to their own prefix and nobody collides.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvConfig:
    name: str
    base_path: str
    namespace: str
    master: str
    features: frozenset[str]

    def source(self, *parts: str) -> str:
        """Shared, read-only inputs. Never namespaced -- every env reads the same raw data."""
        return self._join(self.base_path, *parts)

    def output(self, *parts: str) -> str:
        """Pipeline outputs. Namespaced in dev so concurrent developers never overwrite."""
        segs = (self.namespace, *parts) if self.namespace else parts
        return self._join(self.base_path, *segs)

    def enabled(self, flag: str) -> bool:
        """Activation switch, so deploying code and releasing behaviour stay separate."""
        return flag in self.features

    @staticmethod
    def _join(base: str, *parts: str) -> str:
        tail = "/".join(p.strip("/") for p in parts if p)
        base = base.rstrip("/")
        return f"{base}/{tail}" if tail else base


def load() -> EnvConfig:
    raw_features = os.environ.get("DATAOPS_FEATURES", "")
    return EnvConfig(
        name=os.environ.get("DATAOPS_ENV", "local"),
        base_path=os.environ.get("DATAOPS_BASE_PATH") or os.environ.get("DATA_DIR") or "data",
        namespace=os.environ.get("DATAOPS_NAMESPACE", ""),
        master=os.environ.get("SPARK_MASTER", "local[*]"),
        features=frozenset(f.strip() for f in raw_features.split(",") if f.strip()),
    )
