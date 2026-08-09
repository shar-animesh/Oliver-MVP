"""Pacer — lifecycle cadence, stall detection, and gate-to-gate advancement."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from oliver_core.schemas import DIStage, GateDecision
from oliver_core import audit

STAGE_ORDER = ("DI1", "DI2", "DI3", "DI4", "DI5")
STAGE_TARGET_DAYS = {"DI1": 14, "DI2": 21, "DI3": 30, "DI4": 45, "DI5": 60}   # expected cadence


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Cadence(BaseModel):
    stage: str
    days_in_stage: int
    target_days: int
    days_to_target: int          # target - elapsed (negative = overdue)
    stalled: bool
    reminder: Optional[str] = None


def cadence_for(stage: str, stage_entered_at: datetime, now: Optional[datetime] = None) -> Cadence:
    now = now or _now()
    days = (now - stage_entered_at).days
    target = STAGE_TARGET_DAYS.get(stage, 21)
    stalled = days > target
    reminder = (f"In {stage} for {days}d (target {target}d) — "
                f"{'overdue, needs attention' if stalled else 'on track'}.")
    return Cadence(stage=stage, days_in_stage=days, target_days=target,
                   days_to_target=target - days, stalled=stalled, reminder=reminder)


def next_stage(stage: str) -> Optional[str]:
    i = STAGE_ORDER.index(stage)
    return STAGE_ORDER[i + 1] if i + 1 < len(STAGE_ORDER) else None


def advance_on_pass(sub, now: Optional[datetime] = None, actor: str = "system") -> bool:
    """Advance a pilot that passed its gate to the next stage; records a mesh event."""
    a = sub.assessment
    if not a or a.verdict.gate_decision != GateDecision.GATE_PASS:
        return False
    nxt = next_stage(sub.input.current_stage.value)
    if nxt is None:
        return False                                   # already at DI5
    frm = sub.input.current_stage.value
    sub.input.current_stage = DIStage(nxt)
    sub.stage_entered_at = now or _now()
    audit.record("stage_advanced", subject=str(sub.id), payload={"from": frm, "to": nxt}, actor=actor)
    return True
