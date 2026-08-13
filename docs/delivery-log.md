# Oliver MVP — Delivery Log

Incremental evolution of the MVP toward the intended Oliver Lifecycle Mesh, one
Delivery Squad iteration at a time. Governing rule: **the system works at every step.**

Target execution path: `Oliver Email → Power Automate → HTTP Function → Durable
Functions (agent fan-out) → Canonical Scoring Service → Storage → Read API →
Dashboard`, with Herald emailing the rendered report back. Migration ordering fixed
in the migration analysis; this log tracks its execution.

---

## Iteration 1 — Extract `oliver-core` (shared core package)

**Status:** ✅ complete · **Type:** structural relocation, zero logic change

### Why this first
The dependency root of the whole migration. The Function (Iteration 3) and the
durable store (Iteration 2) must import a shared, framework-free core — not
`app.services.*` — or they would be built against imports that immediately have to
change. Extracting the core once, up front, means every later step re-points nothing.

### Planner
- Move the four **pure** modules — `schemas`, `mock_assessor`, `report`, `store`
  (+ `RUBRIC.md` + the test suite) — into an installable `oliver-core` package.
- **Pure move only.** No assessment, scoring, rendering, or summary logic edited —
  the sole change is `import` paths. Behavior is provably identical because the code
  is byte-identical.
- **Deferred on purpose:** the `StorageBackend` interface (that is the point of
  Iteration 2), splitting `mock_assessor` into engine/evaluators (belongs to the
  real-agent iteration), and trimming the app to a read-only API (Iteration 4).
- Out of scope: durable storage, the Function, read/write split, agents, frontend,
  auth/CORS.

### Builder
- Created `packages/oliver-core/` with `oliver_core/{schemas,mock_assessor,report,store}.py`,
  `RUBRIC.md`, `__init__.py` (public API re-exports), and `pyproject.toml`.
- Re-pointed intra-core imports `app.models.schemas → oliver_core.schemas` and
  `app.services.mock_assessor → oliver_core.mock_assessor`.
- Re-pointed the one consumer, `backend/app/routers/submissions.py`, to import from
  `oliver_core`.
- Removed the vacated `backend/app/models`, `backend/app/services`, `backend/tests`.
- `backend/requirements.txt` now depends on `oliver-core` (editable, from the monorepo);
  `pydantic` is transitive.
- Swept a stray empty `{backend` directory from an earlier heredoc.

### Tester
- Contract suite (26 tests) run from inside the package: **26 passed**.
- Backend boots on the new imports; create → assess → download-report → 409-guard
  all pass via `TestClient` (GATE_PASS 97, report 200 w/ attachment headers, guard 409).
- Residual-import sweep across the repo: **none** (`from app.models` / `from app.services` all gone).
- `oliver-core` imports standalone; its only runtime dependency is `pydantic` —
  confirming the core is genuinely framework-free.

### Result — repository shape after Iteration 1
```
oliver-mvp/
  packages/oliver-core/        # NEW — the framework-free core
    oliver_core/  schemas.py  mock_assessor.py  report.py  store.py  RUBRIC.md  __init__.py
    tests/        test_scoring.py
    pyproject.toml
  backend/                     # FastAPI host — now imports oliver_core (unchanged behavior)
    app/  main.py  routers/{health,submissions}.py
    requirements.txt
  frontend/                    # unchanged
  Dockerfile  k8s/  README.md
```

### What this unlocked
`oliver-core` is now importable by any host. Iteration 2 (durable storage behind the
`store` interface) and Iteration 3 (the HTTP Function wrapping `assess_submission`)
can both build against the shared core with no further import churn.

### Next task → Iteration 2 — Durable storage behind the `store` interface
Introduce a storage backend abstraction in `oliver_core.store` (protocol + the
existing in-memory impl as the local/test backend), selected by environment, with a
durable impl (Cosmos/Table for records, Blob for reports) added beside it. Callers —
including the report endpoint — stay unchanged; the win is persistence and the seam
the Registrar needs. Keeps the system working: default stays in-memory until the
durable backend is configured.

---

## Iteration 2 — Durable storage behind the `store` abstraction

**Status:** ✅ complete (SQLite durable backend proven) · Cosmos scaffolded, deployment-validated
**Type:** additive — one module changed, all contracts preserved

### Planner
Make records survive a restart, behind the existing `store` surface, without touching
any caller. The sandbox has no Azure account, so the provable durable backend is
**SQLite** (stdlib, survives restart); **Cosmos** is the production target, added as a
guarded implementation of the same protocol and validated at deployment.

### Builder — the one-file change
`oliver_core/store.py` only:
- `StorageBackend` **Protocol** (`get` / `put` / `list_all`).
- `MemoryBackend` — the original in-memory logic (default; local + tests).
- `SqliteBackend` — durable single-file store; each `Submission` persisted as its JSON
  document (`id`, `created_at`, `state`, `doc`); point-read by id, list by `created_at desc`.
- `CosmosBackend` — production target; **lazy** `azure-cosmos` import, keyless
  (managed-identity) branch preferred; marked `pragma: no cover` — not exercised locally.
- Env-driven selection (`OLIVER_STORE = memory | sqlite | cosmos`), cached, with
  `set_backend` / `reset_backend` for tests.
- **Module-level `get` / `put` / `list_all` retained as delegators** → the router,
  schemas, report renderer, and frontend are **unchanged**.
`pyproject.toml` gained an optional `cosmos` extra. Default/SQLite paths remain pydantic-only.

### Tester — evidence
- Contract suite on the default memory backend: **26 passed**.
- Core imports with **no `azure` installed** (pydantic-only path intact).
- **Cross-process durability (the real proof):** process A created + assessed a
  submission on SQLite and exited; a **fresh** process B read it back — assessment,
  rating, and all summary fields intact — and **re-rendered the report (HTTP 200) from
  the durable record**. `list_all()` saw the record; the row is on disk.
- Selecting `cosmos` without the SDK raises a clear, safe error.

### Architectural implications
- **The Registrar seam is now real.** Records persist behind a stable interface; the
  Function (Iteration 3) has a durable target to write to.
- **Cosmos is a configuration swap, not a rewrite.** SQLite and Cosmos share identical
  (de)serialization (`Submission.model_dump_json` ⇄ `model_validate*`); the local durable
  backend is a faithful stand-in for Cosmos's document model.
- **Reports stay rendered-on-read** from the durable record — no report artifact store
  yet. Correct for now: on-read guarantees freshness and adds no storage.
- **Core dependency surface preserved.** `azure-cosmos` is optional; nothing but pydantic
  is required unless `OLIVER_STORE=cosmos`.

### Remaining blockers / deferred
1. **Cosmos not integration-tested in this environment** (no Azure account / restricted
   network). The backend is structurally complete and guarded; it must be validated
   against a live Cosmos account at deployment. **Headline blocker.**
2. **Report-artifact persistence (Blob + WORM)** deferred — pre-rendering the report to
   immutable Blob is coupled to Herald (email-back needs the artifact ready) and to the
   audit-trail WORM requirement. Decide in the Herald iteration.
3. **Concurrency / multi-worker.** SQLite + a process-local write lock suits a single
   local instance, not horizontally-scaled hosts. Production durability is Cosmos, which
   removes this; do not run multi-worker SQLite in prod.
4. **Secrets & identity for Cosmos.** Endpoint/key via env today; production posture is
   managed identity with account keys disabled (already the keyless code path) + Key Vault.
5. **Stored-schema evolution.** No versioning/migration of persisted JSON documents yet —
   flag before the record shape changes in a durable environment.
6. **Audit trail** (append-only + per-record hash + WORM mirror) still absent — records
   are durable, but the separate immutable audit store from the plan is a later iteration.

### Next task → Iteration 3 — HTTP-triggered Function (ingest + assess)
Build the HTTP Function that imports `oliver-core`, accepts a submission payload,
normalizes it (email → `SubmissionCreate` via a new `ingest` adapter), runs
`assess_submission`, and writes via `store.put` (now durable). The handler logic is pure
Python and provable by direct invocation here; the Azure Functions host (`function_app.py`,
`host.json`) and the Power Automate → Function wiring are documented as deployment steps
and validated in Azure. Idempotency on the email message-id becomes a first-class concern.

---

## Iteration 3 — HTTP-triggered ingestion path (email → assess → durable store)

**Status:** ✅ complete (handler + FastAPI host + Function scaffold proven) · Azure host & Power Automate = deployment
**Type:** additive — ingestion is new; nothing existing changed behaviour

### Planner
Introduce ingestion as **host-agnostic logic in `oliver-core` with thin adapters** —
the same pattern used for the pipeline. Power Automate posts to whichever host, so
local→Azure is deployment/config, not a rewrite.

### Builder
- **`oliver_core/ingest.py`** (new, host-agnostic): `InboundEmail` / `IngestResult`
  contracts; `normalize()` (strips `Re:`/`Fwd:`, quoted reply chains, `>` history,
  signature blocks, mobile-sig lines); `find_by_message_id()`; and `ingest_email()`,
  which orchestrates **idempotency → normalize → persist → delegate-to-assess**.
- **Separation:** `ingest_email` takes an injectable `assess_fn` (default
  `assess_submission`). Ingestion never reimplements scoring; swapping synchronous
  scoring for "enqueue to a Durable orchestrator" is a one-argument change.
- **Provenance on the record:** `Submission` gained `source` ("web" | "email") and
  `source_message_id` (the idempotency key) — additive, defaulted, backward-compatible.
- **`backend/app/routers/ingest.py`** (new): `POST /api/v1/ingest/email`, a thin host
  over `ingest_email` → 201 created / 200 duplicate. Wired into `main.py` (one line).
- **`services/ingest-func/`** (new): the Azure Function deployment target
  (`function_app.py` HTTP trigger, `host.json`, `requirements.txt`, `local.settings.json`,
  `.funcignore`) — a thin adapter over the SAME `ingest_email`.

### Tester — evidence
- Contract suite: **26 passed**.
- Normalization strips `Re:`/`Fwd:`, signature, and quoted history; keeps the real content.
- **Duplicate handling:** same message-id twice → 201 *created* then 200 *duplicate*, same
  submission id, exactly one record, **no double-assessment**.
- **Cross-process (SQLite):** process A ingested + exited; a fresh process B read the record
  through the dashboard path (source=email, assessed, report HTTP 200), and re-delivering the
  same message-id with a **different body** returned the same record as a duplicate — so
  **idempotency survived the restart and keys on the message-id, not the payload**.
- **Coexistence:** the existing web create/assess flow still works; the dashboard list shows
  both `web`- and `email`-sourced records.
- **Azure compatibility:** `function_app.py` imports against the real `azure-functions` SDK,
  route registered, handler confirmed to be the shared `oliver_core.ingest` object.

### Architectural implications
- **The ingestion boundary now exists.** Power Automate points at the FastAPI URL today or the
  Function URL in Azure — same handler, so the switch is deployment/config.
- **The async window is modelled.** A record is persisted `ASSESSING` before scoring completes,
  which is exactly what email-first ingestion produces and what the 409 report-guard covers.
- **The Durable seam is ready.** `assess_fn` injection is the exact point where synchronous
  scoring becomes "enqueue → Durable orchestrator" when real agents arrive — no rewrite.

### Remaining blockers / deferred
1. **Idempotency lookup is a scan** (`list_all`) — O(n), and scan-then-write is not atomic.
   Production must **point-query the message-id** (Cosmos `WHERE` / a unique key) and enforce
   it atomically to close the concurrent-delivery race. **Headline blocker.**
2. **Assessment is still synchronous inside ingest** — correct for the fast, deterministic mock;
   real (LLM) agents need enqueue → Durable orchestrator via the `assess_fn` seam.
3. **Azure Functions runtime not executed here** — only the handler logic and SDK import are
   proven. The host/trigger and Power Automate wiring are validated at deployment. Packaging
   `oliver-core` for `func publish` (wheel/private feed or vendoring — not editable paths) is a
   deployment task.
4. **The Power Automate flow** is a definition to build in the M365 tenant (mail trigger → parse
   → POST + function key; move mail to Processed/Failed) — not repository code.
5. **Function auth & secrets** — function-level key + Key Vault reference; not wired in-sandbox.
6. **Normalization is intentionally minimal** (subject + cleaned body). Structured-body parsing
   (labeled fields, attachment handling) is a future enhancement.

### Next task → Iteration 4 — Read/write split + edge hardening
Trim the dashboard API to **reads over storage** (`GET /submissions`, `/{id}`, `/{id}/report`),
demote the synchronous write path to an explicit Door-B **`/test-assess`** harness, make email
ingestion the primary write path, and close the open edges from the MVP era (CORS `*` → locked;
add auth on ingest + dashboard). Frontend: `App.jsx` refresh → polling; the Test page becomes the
admin harness. Keeps working at every step — reads and the report are unchanged; only the write
surface and origins tighten.

---

## Iteration 4 (reassessed) — Assessment orchestration seam (Durable + real-agent prep)

**Status:** ✅ complete · **Type:** structural refactor, behavior + contracts preserved

### Planner — reassessment (priorities re-scored against migration-cost reduction)
The prior "read/write split" was re-examined and **deprioritized**: it is production
hardening, not architectural relocation — nothing downstream depends on it and it is
equally cheap later (low migration leverage). The **orchestration seam** was chosen instead:
it is the shared **dependency-root of the two biggest, riskiest remaining gaps** — the Durable
Functions move *and* real LLM agents both flow through it — and it is only cheap to establish
**now**, while the pipeline is a deterministic, fully test-covered mock. Weights-as-data was
acknowledged as a real dependency-root but a narrower axis, sequenced next.

### Builder
- **`AgentScore`** added to schemas — one agent's SubScore *before* weighting (the contract a
  Foundry agent emits / a Durable activity returns).
- **Agent registry** (`AGENTS`) in `mock_assessor.py` — the five mock evaluators (bodies
  **untouched**, still returning tuples) are wrapped into `Agent = (SubmissionCreate) → AgentScore`
  callables carrying dimension identity. **This list is the swap point for real agents and the
  fan-out set a Durable orchestrator drives.**
- **`consolidate()`** extracted — the Canonical Scoring Service boundary (scoring engine +
  StageMaster) as a pure function `(agent scores, stage) → (dimension scores, verdict, stage)`.
- **`assess_submission`** reduced to thin, **I/O-free composition**: fan-out → consolidate →
  coach → summarize. No I/O in the orchestrator body — the exact shape a Durable orchestrator requires.
- Physical module separation (scoring.py / agents.py / orchestrator.py) is a cosmetic follow-up;
  the load-bearing seam is established in place.

### Tester — evidence
- Contract suite: **26 passed** (behavior preserved; composite still 97 for the rich fixture; `≥70` renders).
- Each agent is **independently invocable** → `AgentScore` (no weight — a consolidation concern).
- `consolidate()` is a **pure function** (weights applied, verdict produced).
- **The payoff:** swapping the Idea-Quality agent for a stub **via the registry** recomputed the
  composite (97 → 61) with the **orchestrator and consolidate untouched** — real agents slot in.
- **Regression:** the `Assessment` shape is identical, so report (HTTP 200), ingest (201), and the
  dashboard read path are unaffected.

### Architectural implications — the Durable move is now mechanical
- **`AGENTS` → Durable activities** (parallel fan-out); **`consolidate()` → a CSS activity**;
  **`assess_submission` → the Durable orchestrator** (already I/O-free). The restructuring the
  migration analysis warned about ("asyncio.gather → Durable is not a drop-in") is now done —
  only the invocation mechanism remains to change.
- **Real agents = replace a registry entry** (proven). `AgentScore` is the emit contract.
- `AgentScore` is pipeline-internal (not stored on the record), so storage/report/dashboard are untouched.

### Remaining blockers / deferred
1. **Durable runtime not yet adopted** — this iteration is the *seam/prep*; adopting the Durable
   Functions runtime (and the queue in front of it) is a later, Azure-bound iteration. The
   orchestrator is registry-driven and I/O-free, i.e. ready.
2. **Real agents (Foundry)** — the swap point is ready; the integration is Azure-bound.
3. **weights-as-data (F)** — the next in-sandbox-provable dependency-root (versioned weight-set,
   HITL activation, reproducibility). Now cleanly sequenceable.
4. **read/write split + security (B)** — still pending; production hardening to land before/at deployment.
5. **stage flexibility (G)** — `ASSESSMENT_STAGE` is still fixed to DI1.
6. **Physical module split** — optional cosmetic tidy-up (scoring/agents/orchestrator files).

### Next task → Iteration 5 — Weights-as-data
Externalize `WEIGHTS_BY_STAGE` (and the model/weight-set versions) from Python constants into
**versioned, loadable weight-set data** read by the scoring engine, with a default baked in so
the system keeps working. This is the "single most important production call" from the analysis —
it enables reproducibility, safe back-testing, and the Phase-5 self-improving loop's HITL-activated
re-tuning — and it is fully provable locally. (read/write split + security proceeds in parallel as
a production-readiness track; the Durable runtime and real agents follow once in Azure.)

---

## Iteration 5 — Weights-as-data

**Status:** ✅ complete · **Type:** additive (data + loader); default behavior preserved

### Planner
Externalize the stage weights from a Python constant into versioned, loadable data the
scoring engine resolves at runtime — the "single most important production call" from the
analysis. Default bundled set = behavior preserved; reproducibility, back-testing, and
HITL re-tuning fall out for free.

### Builder
- **`WeightSet`** contract (schemas via `weights.py`) — version + model_version + per-stage
  weights, **validated so each stage sums to 100**.
- **`oliver_core/data/weight-set-3.1.0.json`** — the current table, now bundled data.
- **`oliver_core/weights.py`** — a registry/loader: `active_weight_set` / `get_weight_set` /
  `list_weight_sets` / `register` / `set_active` / `reset`, bundled-default loading, and
  **`OLIVER_WEIGHTS_DIR`** for external sets with **no code deploy**.
- **Engine reads a weight-set, not a constant.** `run_scoring_engine` and `consolidate` take an
  optional `weight_set` and default to the active one; the verdict now records the **actual
  weight-set + model version used**. `WEIGHTS_BY_STAGE` remains as a data-derived compat alias.
- `pyproject.toml` package-data ships the bundled JSON in the wheel.

### Tester — evidence
- Contract suite: **26 passed** (default behavior identical).
- Weights come from data (`weight-set/3.1.0`; DI1 idea-quality = 40; compat alias derives from data).
- **Back-testing:** identical synthetic agent scores → composite **69** (default) vs **54**
  (exec-heavy), each recording its version.
- **Reproducibility:** re-scoring from the recorded version reproduces the composite exactly.
- **HITL activation seam:** `set_active` switches what the pipeline uses by default (54 ↔ 69).
- **Validation:** a weight-set whose stage ≠ 100 is rejected.
- **No-deploy load:** a JSON dropped into `OLIVER_WEIGHTS_DIR` appears in the registry.
- **Regression:** record shape unchanged; report/ingest/dashboard unaffected; version sourced from data.

### Architectural implications
- **The self-improving loop is now unblocked structurally:** tune a candidate → `register` →
  back-test against history → **HITL-activate** — all via the same data + seam.
- **Every record's `weight_set_version` is now meaningful** — it maps to concrete, reloadable weights.
- Weights change is a **data/activation event**, not a code deploy — exactly the target posture.

### Remaining blockers / deferred
1. **Activation is not yet audited / split-permission.** `set_active` is the seam; wrapping it in
   an append-only audit + governance (approval, who/when) is the **audit-trail** iteration.
2. **Weight-set persistence.** Bundled/file today; production should store candidate + active sets
   durably (Cosmos/Blob) and version them there, with cross-instance propagation of the active choice.
3. **Scoring-model params still code.** Gate/completeness/confidence thresholds remain constants — a
   future "scoring-model as data" extension if desired.
4. **Active selection is process-global in memory** — multi-instance activation needs a shared store.

### Next task → Iteration 6 (candidate) — Read/write split + edge hardening
The standing production-readiness item: trim the dashboard API to reads over storage, make
ingestion the primary write path (keep a Door-B `/test-assess`), lock CORS, add an auth seam;
frontend refresh → polling, Test page → admin harness. Other locally-provable candidates if we
re-rank: **audit trail (D)** — now with a concrete consumer (weight-set activation + decision
events), arguably higher *architectural* value than hardening — and **stage flexibility (G)**.
The Durable runtime (A) and real Foundry agents (C) remain seam-ready but Azure-bound.

---

## Iteration 6 — Audit trail & governance foundation

**Status:** ✅ complete (tamper-evidence proven locally) · WORM/immutable backend deferred to deployment
**Type:** additive infrastructure + side-effect instrumentation; behavior + record shape preserved

### Planner — re-rank by architectural leverage (not momentum)
Ranked the three remaining locally-provable options against **governance + traceability + mesh**:
**audit trail ≫ stage flexibility > read/write split**. The audit trail is the only option high on
all three axes, it is the literal governance+traceability foundation and the mesh's event substrate,
and — decisively — it **closes the hole Iteration 5 opened**: weight-set activation changed how every
pilot is scored with no attributable record. Read/write split is deployment hardening (near-zero on
the criterion — the "momentum" option); stage flexibility is a genuine but narrower mesh step, better
sequenced *after* the trail so transitions are recorded from their first occurrence.

### Builder
- **`oliver_core/audit.py`** — append-only, **hash-chained** event log. `AuditEvent` carries
  `seq / event_type / at / subject / actor / payload / prev_hash / hash`; each hash chains to the
  previous, so any later edit breaks the chain. Backends: `MemoryAuditBackend` (default) and
  `JsonlAuditBackend` (durable, append-only, WORM-shaped), env-selected (`OLIVER_AUDIT`). `verify()`
  recomputes the chain and returns the first broken seq. Convenience recorders for decisions,
  ingest, and governance actions.
- **Governance closed:** `weights.set_active(version, actor)` now records a `weight_set_activated`
  event (from/to/actor) — the Iteration 5 hole is closed.
- **Decisions instrumented:** the create + assess routes and the ingest path record
  `submission_received` and `assessment_completed` (composite, gate, assigned stage, HITL flag,
  **weight_set_version**, model_version).
- **Traceability surfaced:** `GET /api/v1/audit` (the trail) and `GET /api/v1/audit/verify`
  (integrity) — read-only.

### Tester — evidence
- Contract suite: **26 passed**; report path unaffected (regression green).
- Events recorded on **both** paths + the **governance** action; `assessment_completed` carries the
  weight-set version; activation carries from/to/actor.
- Chain **verifies** (ok=True over 6 events).
- **Durable + tamper-evident:** events written on JSONL survive a restart (verify=True); forging a
  recorded composite to 999 without recomputing the hash makes `verify()` fail at exactly that seq.

### Architectural implications
- **Governance foundation exists.** The governed action is attributable and traceable; HITL overrides
  and future governance actions record through the same log.
- **Traceability is real** — an ordered, append-only, hash-verified decision record.
- **Mesh substrate.** Stage transitions, revives, and retires become auditable events as those
  capabilities land — the log is the spine they hang on.
- **Tamper-evidence is provable now**; the immutable **storage backend** (Blob immutability / Cosmos
  append) slots behind `AuditBackend` at deployment — the same seam pattern as the record store.

### Remaining blockers / deferred
1. **WORM / immutable storage backend** — JSONL proves the append-only + hash shape; production needs
   the immutable store behind `AuditBackend`. **Headline.**
2. **Actor identity from auth** — `actor` is currently caller-supplied / "system"; real attribution
   arrives with the **auth seam** (the read/write-hardening iteration completes governance here).
3. **Fail-open vs fail-closed policy** — decide explicitly that *governance* actions fail-closed if
   they cannot be audited (no un-audited activation), while keeping the hot path resilient.
4. **Single-instance chain** — multi-instance needs a shared append point + ordering (Cosmos append).
5. **More event types** (stage transition, override, report rendered, email sent) as those land.
6. **No audit UI** yet — endpoint only; dashboard surfacing is a frontend follow-up.

### Next task → Iteration 7 (candidate) — Stage flexibility (2nd in the re-rank, now well-sequenced)
Assess at the submission's **real DI stage** rather than fixed DI1, and record the stage
assignment/transition as an audit event — advancing the mesh's multi-stage nature with transitions
captured from the start. The **read/write split + auth seam (B)** remains the production-readiness
track and would give the audit trail **real actor identity** (a governance-completing coupling). The
Durable runtime (A) and real Foundry agents (C) stay seam-ready but Azure-bound.

---

## Iteration 7 — Stage flexibility

**Status:** ✅ complete · **Type:** small behavioral change + audit event; default preserved

### Planner
Assess at the submission's **real DI stage** (with that stage's weights) instead of fixed DI1,
and record any stage change as a mesh transition on the audit trail — 2nd in the re-rank, now
well-sequenced so transitions are captured from their first occurrence. The engine was already
stage-parameterized; only the caller hardcoded DI1.

### Builder
- **`SubmissionCreate.current_stage: DIStage = DI1`** — the DI gate being assessed (defaults to
  DI1 for new ideas; additive, backward-compatible).
- **Orchestrator** assesses at `sub.current_stage` (was `ASSESSMENT_STAGE`).
- **Reject holds at the assessed stage** (`DIStage(stage)`, was hardcoded DI1) — correct for higher
  stages, identical for DI1.
- **Audit** now records `assessed_stage` alongside `assigned_stage` in `assessment_completed`, and
  emits an explicit **`stage_transition`** (from→to, gate) whenever the stage changes.

### Tester — evidence
- Contract suite: **26 passed** (default DI1 unchanged).
- **Stage-weighted verdicts:** identical scores → **PASS @ DI1 (70)** vs **NO_GO @ DI4 (55)**.
- **Transition recorded:** a DI4 no-go emits `stage_transition` DI4→DI3, and `assessment_completed`
  carries assessed=DI4 / assigned=DI3.
- **Default preserved:** a stage-less submission is assessed at DI1.
- **Regression:** the API accepts `current_stage`, stores it, assesses, renders the report, and the
  audit chain still verifies.

### Architectural implications
- **The mesh's multi-stage nature is now exercised** — the same idea is judged differently at DI1 vs
  DI4, using stage-adaptive weights; assessment is stage-relative, not DI1-only.
- **Transitions are first-class mesh events** on the audit trail (built directly on Iteration 6).

### Remaining blockers / deferred
1. **Lifecycle auto-progression** — pass at DIn assigns DIn (validated-at semantics); *advancing* a
   passed pilot to DIn+1 for its next gate over time is a lifecycle-progression concern, not done.
2. **Stage as tracked lifecycle state** — stage is caller-declared per assessment; a pilot's real
   current stage should be tracked on the record/lifecycle over time (mesh state), not just declared.
3. **Pacer** (cadence / stall detection across stages) still absent.

### Next task → Iteration 8 (candidate) — Read/write split + auth seam
The production-readiness track that also **completes governance attribution**: trim the dashboard API
to reads over storage, make ingestion the primary write path (keep a Door-B `/test-assess`), lock
CORS, and add the auth seam — which finally gives the audit trail **real actor identity** in place of
"system". Herald delivery is the other locally-partial option; the Durable runtime and real Foundry
agents remain Azure-bound.

---
## Iteration 8 — Auth seam + edge hardening (read/write-split, part 1)
Files: backend/app/auth.py (new), main.py (CORS locked to OLIVER_CORS_ORIGINS), routers/submissions.py (actor injected), oliver_core/audit.py (recorders take actor).
Tested: 26 contract tests; actor-identity flow; anonymous default; CORS non-wildcard.
Result: all pass — audit events now carry real actor identity (X-Oliver-Actor → e.g. anand@se; "anonymous" default); CORS origin-restricted.
Impact: completes governance attribution (audit "system" → real actor); closes the wildcard-CORS edge. Read-only API trim + Door-B /test-assess + JWT validation remain (route-trim deferred to avoid frontend churn now).

---
## Iteration 9 — Read/write split completed (auth enforcement + Door-B test-assess)
Files: backend/app/auth.py (bearer-token identity path + require_writer, env-toggled), routers/submissions.py (writes use require_writer; new POST /test-assess).
Tested: 26 contract tests; read-open; Door-B /test-assess; enforcement toggle (anon write 401 when OLIVER_REQUIRE_AUTH on, 201 off; authed write 201; reads 200 either way).
Result: all pass. Reads are open; writes are gated (off in local dev, on in prod); JWT validation plugs into _validate_bearer.
Impact: dashboard API is now read-first with an enforceable write boundary and a Door-B synchronous harness; ingestion remains the production write path (Function-key auth at deployment). Frontend unaffected (enforcement defaults off).

---
## Iteration 10 — Herald delivery seam
Files: oliver_core/herald.py (new: ReportStore memory/file, EmailEnvelope+AttachmentMeta, Deliverer log/graph, deliver_assessment); routers/submissions.py (Door-B POST /deliver).
Tested: 26 contract tests; deliver_assessment via API; report persistence+retrieval by ref; envelope/attachment metadata; report_rendered+email_sent audit events; Graph adapter guarded.
Result: all pass. Report persisted behind ReportStore; delivered via LogDeliverer (channel=log); Graph sendMail scaffolded as deployment adapter; renderer unchanged; no frontend change.
Impact: closes the outbound loop as a host-agnostic seam — Herald renders (existing), persists, envelopes, and delivers; swapping LogDeliverer→GraphDeliverer + memory→file/Blob is config/deployment.

---
## Iteration 11 — Lifecycle progression / Pacer
Files: oliver_core/pacer.py (new: Cadence, cadence_for, next_stage, advance_on_pass); schemas.py (Submission.stage_entered_at); routers/submissions.py (GET /cadence, POST /advance, GET /pacer/stalled).
Tested: 26 contract tests; cadence fresh vs 30d-stalled; next_stage; passing pilot advances DI1->DI2 (stage_advanced audit event, stage_entered_at reset); no-go pilot does not advance; portfolio stall detection.
Result: all pass. Passed pilots advance gate-to-gate; cadence + stall computed per stage; transitions recorded on the audit trail.
Impact: completes the locally-provable mesh surface — pilots now move through DI1->DI5 over time with cadence tracking and stall detection, all auditable.

---
## Final consolidation — Oliver MVP (v18)
Files: README.md (product overview: architecture, API, run guide, config, local-vs-Azure matrix);
frontend/src/api.js (cadence/advance/deliver/audit); frontend/src/pages/Dashboard.jsx (Lifecycle &
Governance panel: cadence, advance, deliver, per-pilot audit trail).
Verified: full end-to-end product smoke (ingest+idempotency → assess+reports → weights back-test →
Herald deliver → Pacer advance+cadence → audit integrity 7 events → auth enforcement) — all pass;
26 contract tests pass; frontend production build clean.
Result: coherent, runnable, documented MVP. Locally-provable architecture complete; Durable
Functions, Foundry agents, and Cosmos/Blob/Graph deployment remain behind ready seams.

---
## Hotfix — Email-prose evidence extraction (root-cause: payload truncation + detector vocabulary)
Root cause confirmed from production screenshots: PathFinder evidence "Scope: 253 chars" = Outlook
bodyPreview truncation — the value/approach/data text never reached the backend. Second cause:
_APPROACH_RE/_DATA_RE vocabulary gaps (no third-person verbs, no spelled-out "Large Language Models"/
"Power Platform", no business-document data nouns). 3-way isolation on the real email:
bodyPreview=18/100 · full body+old detectors=53/100 · full body+broadened detectors=89/100.
Files: mock_assessor.py (_APPROACH_RE: uses/applies/leverages/integrates/based on/powered by +
LLMs/large language models/generative AI/GenAI/GPT*/copilot/RAG/Power Platform/Azure OpenAI/AI-powered;
_DATA_RE: historical/past/existing + proposals/documents/outcomes/contracts/invoices/tickets/emails +
"Data sources:" label pattern). 26 tests green. Power Automate must send full Body (+ Html to text),
not bodyPreview. The experience-parity fix (Anand-style narrative) remains LLM agents via AGENTS registry.

---
## Hotfix 2 — Email HTML sanitization + user-facing assessment quality
Root causes from production screenshots: (1) Power Automate now sends full Body as HTML; backend stored
raw markup (garbage UI, inflated char counts, nonsense one-word citations like "identifying"); (2) evidence
citations quoted the bare regex match, not the containing sentence; (3) strengths/coaching surfaced rubric
internals ("2957 chars", "threshold: 60") and duplicated actions. Score divergence 60 vs 90 decomposed:
the two submissions' texts genuinely differed (web had "30 days" quantifier + pilot; email had no number,
no sponsor — ValuePulse 0 was rubric-correct) + HTML pollution distorted evidence.
Files: ingest.py (_strip_html server-side, flow-independent); mock_assessor.py (_detect cites containing
sentence w/ word-boundary snap; _APPROACH_STRONG_RE preferred for citation; _build_summary strengths prefer
quoted submitter text and hide internals; _COACH_ACTIONS gap→action map + _map_actions dedupe).
Tested: 26 contract tests green; their HTML email → clean text, sentence citations ("We are exploring an
AI-based solution that can analyze available data…"), actionable deduped coaching; web fixture 89 unchanged.
Remaining ceiling: rubric brittleness + narrative quality = LLM agents via AGENTS registry (next milestone).

---
## Herald submitter experience + narrative layer (Phase A)
Created: oliver_core/narrative.py (Narrator seam: TemplateNarrator default/fallback producing all 8
narrated sections grounded in the record; LLMNarrator for Azure OpenAI — config-activated, strict JSON,
grounding-checked, falls back w/ audit event); oliver_core/email_report.py (submitter-facing email in the
historical Oliver format: banner, exec summary, working-well, coaching, AI Approach Guidance, Path to next
gate, Timeline Guidance, score-breakdown table w/ per-dimension commentary, Recommended Next Steps,
resubmission box, HITL note, Oliver Smith sign-off — email-safe tables + inline CSS, all content escaped);
tests/test_narrative_email.py (9 tests). Modified (additive): schemas (AssessmentNarrative +
Assessment.narrative), mock_assessor (attach+lift narrative), ingest (IngestResult.report_html on created
only — duplicates get none so PA can't double-reply), herald (EmailEnvelope.html_body; Deliverer seam
untouched → GraphDeliverer remains the Phase-B swap), submissions router (GET /{id}/report/email preview).
Tested: 35 tests green (26 contract + 9 new); E2E ingest of the real proposal-review email returns the
full submitter report in the response; audit chain verifies; all 15 existing routes intact.
Phase-A delivery: PA replies to sender with body('HTTP')?['report_html'] when status is 201.

---
## Narrative quality redesign — reviewer voice
Root complaint: narrative read as a scoring engine (score-centric exec summary, extraction citations,
generic phrasing, repetition across coaching/steps/milestones). Redesigned TemplateNarrator around
signals -> reasoning: exec summary = problem -> operational impact -> strategic fit -> investment-language
verdict (zero scores); working-well = solution strengths + org benefit + adoption advantages from detected
signals (quantified claim, Microsoft-stack fit, bounded scope, felt problem, data named); coaching
categorized (Missing evidence / Implementation risk / Governance / Stakeholder alignment) each with the
why; approach guidance now justifies WHY + discusses alternatives per problem type; milestones carry
"— proves ..." confidence clauses; timeline explains dependencies (sponsorship critical path, data-access
lead time, measure-before-build); dimension commentary = band+signal reviewer rationale, extraction
language eliminated. Same section briefs written into the LLM narrator prompt so both providers meet the
spec. 33 tests green + 7 quality assertions (no /100 in exec, no "inferred from text" in commentary,
why/alternatives present, proves-clauses present, categories present, greeting stripped).

---
## Evidence traceability — Evidence → Analysis → Recommendation
Audit of v21 found interpretation-as-fact ("absorbing skilled capacity"), assumption-as-fact ("approved
Microsoft estate"), unattributed generalizations ("2–3 weeks"), and one real defect: coaching said
"technical route undefined" while commentary said "route credible" (coaching keyed on raw gap strings,
commentary on resolved signals). Redesign: TemplateNarrator now computes ONE resolved signal set
(_signals: value/baseline/approach/approach-thin/data/scope/stack/sponsor + quotes) that every section
reasons from — contradictions structurally impossible; all sections structured Evidence → Analysis →
Recommendation with four labels (observed / likely·inferred / assumed / projected); generalizations
attributed ("an assumption; verify locally", "a recurring failure mode in the research this program is
built on"); value claims always "projected", unverified premises always "assumed"; coaching items are
Evidence gap → Risk → Action and distinguish "no value claim" from "target stated but no baseline";
schemas gained AssessmentNarrative.evidence_basis (traceability register); email renders a "Grounded in:"
line under the exec summary + a label legend in the footer; the same traceability rules were written into
the LLM narrator prompt. Fixed en route: the narrator quote extractor capped at 90 chars, silently
dropping long approach citations (widened to 180). 39 tests green incl. 6 new traceability tests
(contradiction guard, labels present, projected-value, evidence_basis quotes the submission,
Evidence:/Analysis: structure, grounding+legend rendered).

---
## v23 — Secure the ingestion API (Power Automate integration)
Ask (Anand): protect the backend the Power Automate flow calls; bearer token now,
Entra ID / managed identity later.

Finding: the repo already had an auth *seam* (`backend/app/auth.py`) with an
`OLIVER_REQUIRE_AUTH` switch and a human-`actor` model used by Door-B writes in
`submissions.py`. But (a) the machine ingestion route `POST /api/v1/ingest/email`
was wired to **none** of it, and (b) that seam is attribution, not access control —
the `actor:` bearer stand-in and the `X-Oliver-Actor` header both yield a
non-anonymous actor without any secret. So the Power Automate entry point was open.

Change (Phase A — real shared-secret bearer on the machine route):
- `auth.py`: new `require_ingest_client` — constant-time check of a real
  `OLIVER_INGEST_TOKEN`, fail-closed, 401 on missing/wrong; Entra-JWT seam marked.
- `routers/ingest.py`: endpoint now `Depends(require_ingest_client)`; authenticated
  caller threaded to the audit trail.
- `oliver_core/ingest.py`: `ingest_email(..., actor=...)` for correct attribution.
- `services/ingest-func/function_app.py`: same token check alongside the function
  key (defense in depth; one place for the Entra upgrade).
- `services/ingest-func/local.settings.json`: `OLIVER_REQUIRE_AUTH`,
  `OLIVER_INGEST_TOKEN` scaffolded.
- `backend/tests/test_ingest_auth.py`: 8 tests (off / missing / wrong / actor-stand-in
  / header-bypass / correct / fail-closed / health-open).

Verified: 8 ingest-auth tests pass; 39 oliver-core tests still pass; the fake
`actor:` token and `X-Oliver-Actor` header are both rejected on the ingest route
under enforcement. Human-`actor` seam and Door-B behaviour unchanged.

Not done (Phase B, needs Anand's endpoint + a caller decision): swap the secret
for Entra JWT validation (audience + app role). Known limitation left in place:
`require_writer`'s `X-Oliver-Actor` bypass on Door-B writes — close when Door-B
gets real MSAL user auth, not now (would break future web writes without it).

---
## v24 — Agent + evidence contract, and the provider port (Increment 1)
Deterministic behaviour unchanged. Full workflow (architecture → build → review →
test → docs) executed autonomously. See docs/adr/0001-agent-evidence-contract-and-provider-port.md.

Contract: `AgentScore`→`AgentResult` (typed `Evidence{claim,source_ref,confidence}`,
`reasoning`, `scored_by`). `DimensionScore` gains `evidence_detail` + `scored_by`;
`evidence` becomes a computed `list[str]` projection (report/narrator/frontend
untouched; legacy input rehydrated). `AgentContext` (submission-only) introduced;
`Agent = (AgentContext) -> AgentResult`.

Provider port: `oliver_core/providers/` — `LLMProvider` Protocol + vendor-neutral
Message/CompletionOptions/Completion, `get_provider()` factory (OLIVER_LLM_PROVIDER),
and an Ollama adapter (transport-injected, isolated). Port names no vendor; nothing
outside the adapter+factory knows Ollama. NOT wired to agents (scoring stays
deterministic) — that is Increment 3.

Tests: 69 pass (61 core [39 pre-existing unchanged + 22 new], 8 backend). Determinism,
backward-compat (wire shape + legacy rehydration), forward-compat (LLM/RAG contract
through consolidation), and Ollama isolation (subprocess import checks) all covered.

Config added: OLIVER_LLM_PROVIDER (none|ollama), OLIVER_OLLAMA_BASE_URL, OLIVER_OLLAMA_MODEL.
Debt logged: LLMNarrator still calls Azure OpenAI directly (should move to the port).
Next: Increment 3 (wire LLM agents via the port, per-dimension fallback, shadow-diff);
Increment 2 (transition chokepoint) in parallel.

---
## v25 — LLM evaluators via the provider abstraction (Increment 3)
Deterministic scoring engine unchanged. Full workflow (architecture → build →
review → test → RCA → fix → retest → docs) executed autonomously. See
docs/adr/0002-llm-evaluators-via-provider-abstraction.md.

The five evaluators can now be LLM-scored through the provider port
(OLIVER_AGENTS=llm + a configured provider), with prompts built from the rubric,
structured-JSON → Pydantic validation into the unchanged AgentResult, and
automatic per-dimension fallback to the deterministic evaluator (scored_by=
"llm-fallback") on any failure. Narrator moved onto the same port (LLMNarrator no
longer calls Azure OpenAI directly; generate_narrative is async). Run-level
AssessmentProvenance{provider, model, prompt_version} recorded when LLM-scored;
port gained a vendor-neutral `model` property. shadow_compare added for rubric-vs
-LLM validation. AgentContext / AgentResult / Evidence / SourceRef unchanged;
scoring engine, audit, store, report, frontend unchanged.

Config added: OLIVER_AGENTS (rubric|llm), OLIVER_NARRATIVE_MAX_TOKENS. Ollama stays
isolated behind providers/{ollama,factory}; verified by source scan + subprocess
import tests. Tests: 101 pass (93 core [39 pre-existing unchanged + 54 new], 8
backend). Final challenge added a production safety-net fallback so one dimension
can never crash an assessment. Debt: prompt-rubric transcription, transition
chokepoint (Increment 2), no token/latency telemetry yet.

---
## v26 — Public Oliver v1 API and admin decoupling

The former `packages/oliver-core` project now resides at root `oliver-v1`; the separate development package resides at root `oliver-v2`. V1 keeps the `oliver_core` import contract and now ships its own independently deployable FastAPI host under `oliver_api`.

The public host owns submission CRUD, test assessment, existing-record assessment, both report representations, Herald delivery, Pacer cadence/advance/stall queries, idempotent email ingestion, audit reads and chain verification. Routes are versioned beneath `/api/v1`; health remains `/health`. Runtime settings configure the existing memory/SQLite/Cosmos store, memory/JSONL audit, reports, delivery, weights, and evaluator/provider seams at process startup.

The admin backend no longer imports `oliver_core`, contains Oliver settings, or exposes Oliver workflow routes. It retains only its operational health endpoint and middleware. The React client now builds URLs from `VITE_OLIVER_API_URL` and calls v1 directly; Vite's local `/api` proxy targets v1 on port 8001.

Deployment was repointed to root `oliver-v1`: the Docker image installs dependencies before the local package, starts `oliver_api.main:app` on 8001, and the Kubernetes Deployment/Service use matching names and ports. The Azure ingestion Function's editable development dependency now points to `../../oliver-v1`.

Validation: v1 Ruff checks pass; 3 public-API contract tests pass across every route family, ingestion idempotency, audit integrity, and optional authentication; admin backend lint/format and live route-isolation checks pass; frontend type-check/build pass; a live Vite `/api/v1/test-assess` request reached v1 directly; the v1 Docker image builds and serves health/OpenAPI successfully. Live Azure integrations and production identity remain deployment work.

---

## Oliver v2 deployment boundary

The standalone `services/ingest-func` Azure Function was retired. Oliver v2 exposes its own FastAPI email-response endpoint, and the Terraform-managed Logic App owns the shared-mailbox trigger, API invocation, and same-thread Outlook reply. Historical entries above remain as the record of the former v1 deployment path.
