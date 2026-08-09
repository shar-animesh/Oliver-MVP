"""
Record store — a pluggable backend behind a stable get / put / list_all surface.

The module-level get / put / list_all functions are the contract every caller uses
(the router has not changed since the in-memory era). Behind them sits a selectable
StorageBackend:

    OLIVER_STORE = memory   (default)  in-process dict; local dev + tests
                 = sqlite              durable single-file DB; survives restart
                 = cosmos              Azure Cosmos DB; production target

All backends serialize the SAME Pydantic record (Submission.model_dump_json), so a
record written by one is readable by any other. SQLite and Cosmos share identical
(de)serialization — the local durable backend is a faithful stand-in for the document
model Cosmos uses, which is what makes the Cosmos swap a configuration change.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Optional, Protocol
from uuid import UUID

from oliver_core.schemas import Submission


# ── The abstraction every backend implements ────────────────────────────
class StorageBackend(Protocol):
    def put(self, submission: Submission) -> Submission: ...
    def get(self, submission_id: UUID) -> Optional[Submission]: ...
    def list_all(self) -> list[Submission]: ...


# ── In-memory (default; local dev + tests) — unchanged semantics ────────
class MemoryBackend:
    def __init__(self) -> None:
        self._store: dict[UUID, Submission] = {}

    def put(self, submission: Submission) -> Submission:
        self._store[submission.id] = submission
        return submission

    def get(self, submission_id: UUID) -> Optional[Submission]:
        return self._store.get(submission_id)

    def list_all(self) -> list[Submission]:
        return sorted(self._store.values(), key=lambda s: s.created_at, reverse=True)


# ── SQLite (durable; survives process restart; zero extra dependencies) ──
class SqliteBackend:
    """
    Each Submission is stored as its JSON document in one row
    (id, created_at, state, doc). Point-read by id; list ordered by created_at
    desc — the same access shape as the in-memory backend and as Cosmos.
    """

    def __init__(self, path: str | Path = "oliver-store.db") -> None:
        self._path = str(path)
        self._write_lock = threading.Lock()   # serialize writes for the MVP
        with closing(sqlite3.connect(self._path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS submissions ("
                "  id TEXT PRIMARY KEY,"
                "  created_at TEXT NOT NULL,"
                "  state TEXT NOT NULL,"
                "  doc TEXT NOT NULL)"
            )
            conn.commit()

    def put(self, submission: Submission) -> Submission:
        with self._write_lock, closing(sqlite3.connect(self._path)) as conn:
            conn.execute(
                "INSERT INTO submissions (id, created_at, state, doc) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state=excluded.state, doc=excluded.doc",
                (
                    str(submission.id),
                    submission.created_at.isoformat(),
                    submission.state.value,
                    submission.model_dump_json(),
                ),
            )
            conn.commit()
        return submission

    def get(self, submission_id: UUID) -> Optional[Submission]:
        with closing(sqlite3.connect(self._path)) as conn:
            row = conn.execute(
                "SELECT doc FROM submissions WHERE id = ?", (str(submission_id),)
            ).fetchone()
        return Submission.model_validate_json(row[0]) if row else None

    def list_all(self) -> list[Submission]:
        with closing(sqlite3.connect(self._path)) as conn:
            rows = conn.execute(
                "SELECT doc FROM submissions ORDER BY created_at DESC"
            ).fetchall()
        return [Submission.model_validate_json(r[0]) for r in rows]


# ── Cosmos DB (production target) ───────────────────────────────────────
# NOTE: structurally complete but NOT exercised by local tests — it requires a
# live Azure Cosmos account. Validated at deployment (Iteration 3+). The azure-cosmos
# import is lazy so importing this module never requires the SDK; install the extra
# with:  pip install oliver-core[cosmos]
class CosmosBackend:
    def __init__(
        self,
        endpoint: str,
        key: Optional[str] = None,
        database: str = "oliver",
        container: str = "submissions",
    ) -> None:
        try:
            from azure.cosmos import CosmosClient, PartitionKey
        except ImportError as e:  # pragma: no cover - requires optional extra
            raise RuntimeError(
                "CosmosBackend requires 'azure-cosmos' (pip install oliver-core[cosmos])."
            ) from e

        if key:
            client = CosmosClient(endpoint, credential=key)
        else:
            # Preferred posture: managed identity, account keys disabled.
            from azure.identity import DefaultAzureCredential  # pragma: no cover

            client = CosmosClient(endpoint, credential=DefaultAzureCredential())

        db = client.create_database_if_not_exists(database)
        self._container = db.create_container_if_not_exists(
            id=container, partition_key=PartitionKey(path="/id")
        )

    def put(self, submission: Submission) -> Submission:  # pragma: no cover
        import json

        item = json.loads(submission.model_dump_json())
        item["id"] = str(submission.id)
        self._container.upsert_item(item)
        return submission

    def get(self, submission_id: UUID) -> Optional[Submission]:  # pragma: no cover
        try:
            item = self._container.read_item(
                item=str(submission_id), partition_key=str(submission_id)
            )
        except Exception:  # CosmosResourceNotFoundError and friends
            return None
        return Submission.model_validate(item)

    def list_all(self) -> list[Submission]:  # pragma: no cover
        items = self._container.query_items(
            "SELECT * FROM c ORDER BY c.created_at DESC",
            enable_cross_partition_query=True,
        )
        return [Submission.model_validate(i) for i in items]


# ── Backend selection (env-driven; cached) ──────────────────────────────
_backend: Optional[StorageBackend] = None


def _build_backend() -> StorageBackend:
    kind = os.getenv("OLIVER_STORE", "memory").lower()
    if kind == "memory":
        return MemoryBackend()
    if kind in ("sqlite", "file"):
        return SqliteBackend(os.getenv("OLIVER_STORE_PATH", "oliver-store.db"))
    if kind == "cosmos":
        endpoint = os.environ["OLIVER_COSMOS_ENDPOINT"]
        return CosmosBackend(
            endpoint=endpoint,
            key=os.getenv("OLIVER_COSMOS_KEY"),
            database=os.getenv("OLIVER_COSMOS_DATABASE", "oliver"),
            container=os.getenv("OLIVER_COSMOS_CONTAINER", "submissions"),
        )
    raise ValueError(f"Unknown OLIVER_STORE backend: {kind!r}")


def backend() -> StorageBackend:
    """Return the active backend, building it from the environment on first use."""
    global _backend
    if _backend is None:
        _backend = _build_backend()
    return _backend


def set_backend(b: StorageBackend) -> None:
    """Inject a backend explicitly (used by tests)."""
    global _backend
    _backend = b


def reset_backend() -> None:
    """Clear the cached backend so the next call rebuilds from the environment."""
    global _backend
    _backend = None


# ── Stable module surface — callers unchanged since the in-memory era ────
def put(submission: Submission) -> Submission:
    return backend().put(submission)


def get(submission_id: UUID) -> Optional[Submission]:
    return backend().get(submission_id)


def list_all() -> list[Submission]:
    return backend().list_all()
