# Oliver v1 architecture and agent inventory

This note describes the code that currently exists in root `oliver-v1`. It distinguishes executable assessment agents from orchestration roles and future deployment seams.

## Executable assessment agents

All five agents receive the same immutable `AgentContext`, which currently contains only a `SubmissionCreate`. Each returns the shared `AgentResult` contract with a score, confidence, typed evidence, gaps, reasoning/provenance, and its owned dimension.

| Agent | Owned dimension | Current deterministic responsibility |
|---|---|---|
| DocGuard | `ideaCompleteness` | Checks whether the problem, approach, value, data, sponsor, team, and supporting context are present and substantive. Its score also controls the completeness pre-gate. |
| IdeaPulse | `ideaQuality` | Evaluates problem specificity, quantified impact, consequence, stakeholders, approach fit, and depth. |
| ValuePulse | `strategicValue` | Evaluates explicit and quantified value, efficiency, scale, substance, and baseline evidence. |
| TechScope | `technicalFeasibility` | Evaluates technical approach, data availability, integration surface, and supporting technical context. |
| PathFinder | `executionReadiness` | Evaluates sponsor ownership, team capacity, pilot scope, and execution planning. |

The single `_EVALUATOR_REGISTRY` in `mock_assessor.py` binds agent name, dimension, label, and deterministic evaluator. It builds both the default rubric agents and the optional LLM agents, so ordering is not a correctness requirement; consolidation indexes results by dimension.

## How one assessment runs

```text
SubmissionCreate
      │
      ▼
resolve_agents()
      │
      ├─ default: five deterministic rubric agents
      └─ OLIVER_AGENTS=llm + provider: five LLM agents
                            (per-agent deterministic fallback)
      │
      ▼
asyncio.gather() fan-out
      │
      ▼
five AgentResult records with typed evidence
      │
      ▼
consolidate()
      ├─ stage-specific weights
      ├─ completeness floor (30)
      ├─ composite gate threshold (70)
      ├─ confidence / human-review routing
      └─ StageMaster lifecycle assignment
      │
      ▼
IdeaCoach + summary synthesis
      │
      ▼
TemplateNarrator or LLMNarrator
      │        (grounding guard + template fallback)
      ▼
Assessment
```

With `OLIVER_AGENTS=rubric` (the default), all five evaluators are deterministic evidence-presence rubrics. With `OLIVER_AGENTS=llm` and an `OLIVER_LLM_PROVIDER`, each dimension is rendered from the corresponding rubric into a provider-neutral prompt. The response is extracted as JSON and validated into the same contract. A provider error, malformed JSON, validation failure, timeout, or unexpected per-agent exception falls back only that dimension to its deterministic evaluator and marks it `llm-fallback`.

`consolidate()` is the Canonical Scoring Service boundary. It is pure and does not know whether the inputs came from rubric or LLM agents. The active versioned weight set supplies DI-stage weights. DocGuard below 30 produces `COACHING_REJECT`; otherwise a stage-weighted composite at least 70 passes. Low confidence, a no-go, or an irreversible stage requires human review. StageMaster maps that verdict into the lifecycle state.

After consolidation, IdeaCoach derives gaps and actions, and summary synthesis builds compatibility fields. The narrative layer then produces the submitter-facing explanation. The deterministic `TemplateNarrator` is the default. `LLMNarrator` uses the same provider port when enabled, enforces grounding, and falls back to the template on failure.

## Supporting roles already implemented

- The public `oliver_api` host owns HTTP configuration, CORS, optional auth dependencies, route contracts, and process startup. It delegates domain work to `oliver_core`.
- Ingest normalizes inbound email, enforces message-id idempotency, persists the assessing record, calls the assessment orchestrator, persists the result, and renders the email response.
- The store seam supports memory, SQLite, and Cosmos backends.
- Audit records append-only hash-linked events through memory or JSONL backends and can verify the chain.
- Herald renders and stores reports, builds an email envelope, calls a delivery adapter, and audits delivery. Log delivery works locally; Microsoft Graph is a deployment adapter stub.
- Pacer calculates time-in-stage, detects stalls, and advances passing submissions to the next DI gate.
- Shadow comparison runs rubric and LLM evaluator sets against the same submission without persistence, reporting dimension deltas, fallback dimensions, and gate agreement.

## Important current boundaries

- Azure AI Foundry is not connected. The only implemented concrete model adapter is Ollama; provider interfaces are ready for another adapter.
- The five deterministic evaluators, orchestration, canonical scoring, coaching, and summary synthesis remain concentrated in `mock_assessor.py`. The filename understates how much production logic it now contains.
- The rubric is represented in deterministic code and transcribed into `prompts.py`; keeping those two definitions aligned is manual today.
- LLM execution is concurrent inside one API process, not yet Durable Functions activity orchestration.
- Memory stores are process-local. SQLite is suitable for local single-instance durability, while Cosmos still needs live Azure validation.
- The email idempotency lookup scans submissions and is not an atomic unique insert, so concurrent duplicate delivery remains a production race until the durable store owns a unique message-id constraint.
- The current human writer identity header is an attribution seam, not verified production identity. Entra/MSAL validation is still required.
- Microsoft Graph delivery deliberately raises `NotImplementedError`; live delivery is not complete.
- API startup currently maps validated settings into legacy environment-driven domain factories. A future cleanup can replace that compatibility bridge with explicit dependency injection.

These seams allow the internal files to be rewritten incrementally while preserving `SubmissionCreate → AgentResult → Assessment` and the public `/api/v1` contracts.
