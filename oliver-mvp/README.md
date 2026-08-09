# Oliver — AI Pilot Lifecycle Mesh (MVP)

Oliver assesses AI pilot submissions against a stage-gate protocol, coaches them toward the next
gate, and tracks them through the DI1→DI5 lifecycle — with every decision and governance action
recorded on a tamper-evident audit trail. This repo is the working MVP: a framework-free assessment
core, a FastAPI service, and a React dashboard, built so the remaining production pieces (Durable
Functions, Foundry agents, Cosmos/Blob, Graph email) drop in behind existing seams without rewrites.

## What it does
- **Assess** five canonical dimensions with **stage-adaptive weights** → composite, gate decision,
  DI-stage, confidence.
- **Coach** — executive summary, strengths, coaching recommendations, next actions (summary report)
  + a downloadable **structured report** (complete record).
- **Ingest by email** — host-agnostic, idempotent on the message-id (Power Automate → HTTP).
- **Govern** — weights are **versioned data** (back-testing + HITL activation); every activation,
  decision, ingest, transition, and delivery is on an **append-only, hash-chained audit trail** with
  real actor identity.
- **Progress** — pilots move gate-to-gate over time; **Pacer** tracks cadence + flags stalls.
- **Deliver** — **Herald** renders, persists, envelopes, and delivers the report (Graph sendMail at deployment).

## Architecture
```
Email → Power Automate → HTTP ingest ─┐
                        Dashboard (Door B) ─┤→ pipeline (agents → consolidate/CSS)
                                             │        │
                                             │   weights (versioned · back-test · activate)
                                             ▼        ▼
                                     durable store  —  audit trail (append-only · hash-chained)
                                             │
                     Herald (render · persist · envelope · deliver) · Pacer (cadence · stall · advance)
```
`packages/oliver-core/` (pydantic-only by default): schemas · mock_assessor (agent registry swap
point + consolidate/CSS + I/O-free orchestrator) · weights · report · store (memory/sqlite/cosmos) ·
audit (memory/jsonl) · ingest · herald · pacer.

## API (selected) — reads open; writes gated by `require_writer`
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/ingest/email` | ingest inbound email (idempotent) — production write path |
| POST | `/api/v1/test-assess` | Door-B: create + assess |
| GET | `/api/v1/submissions` · `/{id}` · `/{id}/report` | portfolio · detail · download |
| POST | `/api/v1/submissions/{id}/deliver` | Herald deliver |
| GET/POST | `/api/v1/submissions/{id}/cadence` · `/advance` | Pacer cadence · advance |
| GET | `/api/v1/pacer/stalled` · `/audit` · `/audit/verify` | stalls · trail · integrity |

## Run
```bash
pip install -e packages/oliver-core && pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload      # API :8000
cd frontend && npm install && npm run dev          # dashboard :5173
cd packages/oliver-core && pytest                  # contract suite
```

## Config (env)
`OLIVER_STORE` memory|sqlite|cosmos · `OLIVER_AUDIT` memory|jsonl · `OLIVER_REPORTS` memory|file ·
`OLIVER_DELIVERY` log|graph · `OLIVER_WEIGHTS_DIR` · `OLIVER_WEIGHT_SET` · `OLIVER_REQUIRE_AUTH` ·
`OLIVER_CORS_ORIGINS`.

## Local vs Azure
Built + tested locally: assessment/scoring/coaching/reports, idempotent ingestion, versioned
weights + back-test + HITL activation, hash-chained audit trail, read/write split + auth seam,
Herald (log deliverer), Pacer cadence/stall/advance. Azure-bound (seams ready, scaffolded here):
Durable Functions orchestration, real Foundry agents, Cosmos/Blob-WORM/Graph sendMail, Power
Automate flow + Bicep/CI-CD. See `docs/delivery-log.md`.
