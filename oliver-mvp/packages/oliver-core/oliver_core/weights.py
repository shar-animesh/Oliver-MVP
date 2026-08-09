"""
Weight-sets as versioned, loadable data — "weights are data, not code".

The scoring engine resolves weights from a WeightSet at runtime instead of a
hardcoded table. A default weight-set is bundled so the system works out of the
box; additional sets can be dropped into OLIVER_WEIGHTS_DIR (no code deploy) and
one made active by version. This enables:

  • reproducibility — each assessment records the weight-set version it used, and
    that version reloads to the exact same weights;
  • back-testing — score against any registered set via an explicit argument;
  • HITL re-tuning — activation is a governed event (see set_active), the seam the
    self-improving loop plugs into. In production it is audited + split-permission.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

STAGES = ("DI1", "DI2", "DI3", "DI4", "DI5")
WEIGHT_DIMENSIONS = (
    "ideaCompleteness", "ideaQuality", "strategicValue",
    "technicalFeasibility", "executionReadiness",
)
DEFAULT_VERSION = "weight-set/3.1.0"
_DATA_DIR = Path(__file__).resolve().parent / "data"


class WeightSet(BaseModel):
    """A versioned set of stage-adaptive weights. Each stage must sum to 100."""
    version: str
    model_version: str = "scoring-model/3.1.0"
    weights: dict[str, dict[str, int]]

    @field_validator("weights")
    @classmethod
    def _validate(cls, v: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
        for stage in STAGES:
            if stage not in v:
                raise ValueError(f"weight-set missing stage {stage!r}")
            row = v[stage]
            missing = [k for k in WEIGHT_DIMENSIONS if k not in row]
            if missing:
                raise ValueError(f"stage {stage!r} missing dimensions {missing}")
            total = sum(row[k] for k in WEIGHT_DIMENSIONS)
            if total != 100:
                raise ValueError(f"stage {stage!r} weights sum to {total}, not 100")
        return v

    def weights_for(self, stage: str) -> dict[str, int]:
        return self.weights[stage]


_REGISTRY: dict[str, WeightSet] = {}
_active: Optional[str] = None


def _load_dir(d: Path) -> None:
    if not d.is_dir():
        return
    for f in sorted(d.glob("*.json")):
        ws = WeightSet.model_validate_json(f.read_text())
        _REGISTRY[ws.version] = ws


def _ensure_loaded() -> None:
    global _active
    if _REGISTRY:
        return
    _load_dir(_DATA_DIR)                      # bundled defaults
    ext = os.getenv("OLIVER_WEIGHTS_DIR")
    if ext:
        _load_dir(Path(ext))                  # externally supplied sets — no code deploy
    if not _REGISTRY:
        raise RuntimeError("no weight-sets found — bundled data missing")
    _active = os.getenv("OLIVER_WEIGHT_SET") or (
        DEFAULT_VERSION if DEFAULT_VERSION in _REGISTRY else next(iter(_REGISTRY))
    )
    if _active not in _REGISTRY:
        raise ValueError(f"OLIVER_WEIGHT_SET={_active!r} not found; have {sorted(_REGISTRY)}")


def default_weight_set() -> WeightSet:
    _ensure_loaded()
    return _REGISTRY.get(DEFAULT_VERSION) or _REGISTRY[next(iter(_REGISTRY))]


def active_weight_set() -> WeightSet:
    _ensure_loaded()
    return _REGISTRY[_active]


def get_weight_set(version: str) -> WeightSet:
    _ensure_loaded()
    if version not in _REGISTRY:
        raise ValueError(f"unknown weight-set {version!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[version]


def list_weight_sets() -> list[str]:
    _ensure_loaded()
    return sorted(_REGISTRY)


def register(ws: WeightSet) -> WeightSet:
    """Add a weight-set to the registry (e.g. a newly tuned candidate)."""
    _ensure_loaded()
    _REGISTRY[ws.version] = ws
    return ws


def set_active(version: str, actor: str = "system") -> WeightSet:
    """
    Make a weight-set active for subsequent scoring.

    In production this is a HITL-approved, split-permission event — not a silent
    change — because it alters how every pilot is scored. Activation is recorded
    to the audit trail so the governance action is attributable and traceable.
    """
    global _active
    _ensure_loaded()
    if version not in _REGISTRY:
        raise ValueError(f"unknown weight-set {version!r}; have {sorted(_REGISTRY)}")
    previous = _active
    _active = version
    # Governed action → audit (lazy import keeps the core dependency graph acyclic).
    from oliver_core import audit
    audit.record_weight_set_activated(previous, version, actor=actor)
    return _REGISTRY[version]


def reset() -> None:
    """Clear the registry + active selection so the next call reloads (tests)."""
    global _active
    _REGISTRY.clear()
    _active = None
