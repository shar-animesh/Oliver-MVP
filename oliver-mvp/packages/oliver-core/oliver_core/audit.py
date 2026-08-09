"""
Append-only, tamper-evident audit trail — the governance + traceability foundation.

Every governed action and decision is recorded as an ordered event whose hash is
chained to the previous event's hash. Any later modification breaks the chain, so
verify() detects tampering. This is the local, provable core of the planned
"append-only + per-record hash + WORM mirror" requirement; an immutable storage
backend (Blob immutability / Cosmos append) slots in behind AuditBackend at
deployment without changing callers — the same seam pattern as the record store.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from pydantic import BaseModel

GENESIS_HASH = "0" * 64


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(BaseModel):
    seq: int                       # monotonic position in the chain
    event_type: str
    at: datetime
    subject: str                   # what it concerns: a submission id, or "governance"
    actor: str = "system"          # who: identity from auth once the auth seam lands
    payload: dict = {}
    prev_hash: str                 # hash of the previous event (chain link)
    hash: str                      # sha256 over this event's fields + prev_hash

    def compute_hash(self) -> str:
        body = {
            "seq": self.seq,
            "event_type": self.event_type,
            "at": self.at.isoformat(),
            "subject": self.subject,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }
        blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _make_event(seq, event_type, subject, payload, actor, prev_hash) -> AuditEvent:
    ev = AuditEvent(
        seq=seq, event_type=event_type, at=_utcnow(), subject=subject,
        actor=actor, payload=payload, prev_hash=prev_hash, hash="",
    )
    ev.hash = ev.compute_hash()
    return ev


class AuditBackend(Protocol):
    def append(self, event_type: str, subject: str, payload: dict, actor: str) -> AuditEvent: ...
    def all(self) -> list[AuditEvent]: ...


# ── In-memory (default; local + tests) ──────────────────────────────────
class MemoryAuditBackend:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event_type, subject, payload, actor) -> AuditEvent:
        prev = self._events[-1].hash if self._events else GENESIS_HASH
        ev = _make_event(len(self._events), event_type, subject, payload, actor, prev)
        self._events.append(ev)
        return ev

    def all(self) -> list[AuditEvent]:
        return list(self._events)


# ── JSONL (durable, append-only; survives restart; mirrors the WORM shape) ──
class JsonlAuditBackend:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def _read(self) -> list[AuditEvent]:
        out: list[AuditEvent] = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(AuditEvent.model_validate_json(line))
        return out

    def append(self, event_type, subject, payload, actor) -> AuditEvent:
        events = self._read()
        prev = events[-1].hash if events else GENESIS_HASH
        ev = _make_event(len(events), event_type, subject, payload, actor, prev)
        with self._path.open("a") as f:                 # append-only
            f.write(ev.model_dump_json() + "\n")
        return ev

    def all(self) -> list[AuditEvent]:
        return self._read()


# ── Backend selection (env-driven; cached) ──────────────────────────────
_backend: Optional[AuditBackend] = None


def _build_backend() -> AuditBackend:
    kind = os.getenv("OLIVER_AUDIT", "memory").lower()
    if kind == "memory":
        return MemoryAuditBackend()
    if kind in ("jsonl", "file"):
        return JsonlAuditBackend(os.getenv("OLIVER_AUDIT_PATH", "oliver-audit.jsonl"))
    raise ValueError(f"unknown OLIVER_AUDIT backend {kind!r}")


def backend() -> AuditBackend:
    global _backend
    if _backend is None:
        _backend = _build_backend()
    return _backend


def set_backend(b: AuditBackend) -> None:
    global _backend
    _backend = b


def reset() -> None:
    global _backend
    _backend = None


# ── Public API ──────────────────────────────────────────────────────────
def record(event_type: str, subject: str, payload: Optional[dict] = None,
           actor: str = "system") -> AuditEvent:
    return backend().append(event_type, subject, payload or {}, actor)


def events() -> list[AuditEvent]:
    return backend().all()


def verify() -> tuple[bool, Optional[int]]:
    """
    Recompute the hash chain from genesis. Returns (ok, first_bad_seq).
    Any tampered field or broken link fails verification at the offending seq.
    """
    prev = GENESIS_HASH
    for ev in backend().all():
        if ev.prev_hash != prev or ev.compute_hash() != ev.hash:
            return False, ev.seq
        prev = ev.hash
    return True, None


# ── Convenience recorders (used at the side-effect boundaries) ──────────
def record_submission_received(sub, actor: str = "system") -> AuditEvent:
    return record("submission_received", subject=str(sub.id), actor=actor, payload={
        "source": sub.source,
        "source_message_id": sub.source_message_id,
        "title": sub.input.title,
    })


def record_assessment(sub, actor: str = "system") -> AuditEvent:
    a = sub.assessment
    assessed_stage = sub.input.current_stage.value
    assigned_stage = a.stage.assigned_stage.value if a.stage.assigned_stage else None
    ev = record("assessment_completed", subject=str(sub.id), actor=actor, payload={
        "composite": a.verdict.composite,
        "gate_decision": a.verdict.gate_decision.value,
        "assessed_stage": assessed_stage,
        "assigned_stage": assigned_stage,
        "requires_human_review": a.verdict.requires_human_review,
        "weight_set_version": a.verdict.weight_set_version,
        "model_version": a.verdict.model_version,
    })
    # A stage change is a Lifecycle Mesh transition — record it explicitly.
    if assigned_stage is not None and assigned_stage != assessed_stage:
        record("stage_transition", subject=str(sub.id), payload={
            "from": assessed_stage, "to": assigned_stage,
            "gate_decision": a.verdict.gate_decision.value,
        })
    return ev


def record_weight_set_activated(from_version: Optional[str], to_version: str,
                                actor: str = "system") -> AuditEvent:
    return record("weight_set_activated", subject="governance",
                  payload={"from": from_version, "to": to_version}, actor=actor)
