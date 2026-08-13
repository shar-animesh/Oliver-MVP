# ADR 0001 — Agent + Evidence Contract, and the Provider Port

Status: Accepted · Increment 1 · Deterministic behaviour unchanged

## Context

Oliver is evolving from a deterministic assessment tool into an AI Lifecycle
platform (docs 01–03). Two contracts were about to be baked into the upcoming LLM
work in a shape too narrow to carry it: the agent output (`AgentScore`, with
untyped `evidence: list[str]`) and the agent input (`Callable[[SubmissionCreate], …]`).
Separately, model access needed to be provider-agnostic so Azure OpenAI / Azure AI
Foundry can be adopted later without touching agents, scoring, the coordinator, or
the future Registrar.

This increment reshapes those contracts **while the system is still deterministic**
— the safe window, because outputs are byte-reproducible and give the strongest
regression harness — and adds the provider port as isolated infrastructure. Agents
are **not** wired to a provider here; that is a later increment. The deterministic
scoring engine, the hash-chained audit, and the Pydantic record contracts are
unchanged.

## Decisions

1. **Typed, source-referenceable evidence.** New `Evidence{claim, source_ref,
   confidence}` and `SourceRef{kind, locator}`. `kind ∈ {field, submission_span,
   retrieved_doc}` so RAG grounding slots in by extending a `Literal`, not by
   changing agents.
2. **Richer agent output.** `AgentScore` → `AgentResult` (typed `evidence`,
   optional `reasoning` trace, `scored_by` provenance). Sufficient for LLM, RAG,
   and tool-using agents without further contract change.
3. **Backward-compatible projection.** `DimensionScore` stores typed
   `evidence_detail` (source of truth) and exposes `evidence` as a **computed,
   read-only** `list[str]` projection (`[e.claim …]`). Result: `report.py`,
   `narrative.py`, and the frontend are untouched, and the wire keeps
   `evidence: list[str]` while adding `evidence_detail`. A `model_validator`
   rehydrates any legacy `evidence: list[str]` input into typed form.
4. **Minimal agent input seam.** New `AgentContext` (frozen dataclass) carrying
   only `submission`. Capability seams (`model`, `retriever`, `tools`, `memory`)
   are added **additively** when their consumers exist — none is populated
   speculatively. Introduced now so the input-signature change happens inside the
   safe deterministic refactor, not fused later with LLM behaviour.
5. **Provider port.** `oliver_core/providers/` defines `LLMProvider` (Protocol) +
   vendor-neutral `Message`/`CompletionOptions`/`Completion`, a config-driven
   `get_provider()` factory (single selection point, concrete providers imported
   lazily), and one adapter. The port **names no vendor**. Business logic depends
   only on the port + factory. HTTP is behind an injected transport so adapters
   are testable without a running server and without a hard `httpx` dependency.

## Contracts (summary)

```
SourceRef   { kind: "field"|"submission_span"|"retrieved_doc", locator: str }
Evidence    { claim: str, source_ref: SourceRef, confidence: float }
AgentResult { agent, dimension, dimension_label, value, confidence,
              summary, evidence: [Evidence], gaps: [str], reasoning, scored_by }
AgentContext(frozen) { submission }              # capabilities added additively
Agent       = (AgentContext) -> Awaitable[AgentResult]

LLMProvider (Protocol) { name; async complete(messages, *, options) -> Completion }
get_provider(name?) -> LLMProvider | None        # OLIVER_LLM_PROVIDER: none|ollama
```

`DimensionScore`: adds `evidence_detail: [Evidence]`, `scored_by: str`; `evidence`
is now a computed `list[str]`.

## Files changed

- `schemas.py` — `SourceRef`, `Evidence`, `AgentResult` (replaces `AgentScore`);
  `DimensionScore` evolved (typed detail + computed projection + legacy validator).
- `mock_assessor.py` — `_finalize_checks` emits typed `Evidence`; `AgentContext`;
  `Agent` alias; `_make_agent`/`consolidate`/`assess_submission` on the new contract.
- `__init__.py` — export `Evidence`, `SourceRef`, `AgentResult`, `AgentContext`.
- `providers/` (new) — `base.py` (port + models), `ollama.py` (adapter, isolated),
  `factory.py` (selection), `__init__.py` (public surface = port + factory only).
- Tests (new) — `tests/test_contract_evidence.py`, `tests/test_providers.py`.

## Test & regression evidence

- **69 tests pass**: 61 in `oliver-core` (39 pre-existing, unchanged, + 22 new),
  8 in `backend` (ingest-auth / API path).
- **Regression / determinism**: `test_assessment_is_deterministic_and_rubric_scored`
  asserts two runs produce an identical scoring projection (composite, gate, stage,
  HITL, per-dimension value/confidence/evidence-strings/gaps/provenance). The 39
  pre-existing tests — which read `dim.evidence` as strings — pass unchanged,
  proving the computed projection is behaviour-preserving.
- **Backward compat**: wire-shape test (`evidence` list[str] **and**
  `evidence_detail` both serialized); legacy-rehydration test.
- **Forward compat**: `test_llm_contract_flows_through_consolidation_unchanged`
  builds `AgentResult(scored_by="llm", source_ref.kind="retrieved_doc")` and runs
  it through consolidation — no contract change needed for the LLM/RAG increment.
- **Isolation**: subprocess tests assert importing the core / assessor / factory
  does **not** load `providers.ollama`; source scan confirms Ollama is named only
  in the adapter and the factory branch.

## Migration

No data migration for the default in-memory store. For persisted (sqlite) records,
the `DimensionScore` `model_validator` rehydrates a legacy `evidence: list[str]`
into typed `Evidence` (locator `"legacy"`), so old records keep an evidence view.
Rollback is a single-commit revert: `evidence_detail`/`scored_by` are additive and
`evidence` remains wire-compatible.

## Future Azure OpenAI / Foundry migration

Add `providers/azure_openai.py` implementing `LLMProvider` (chat-completions →
`Completion`; managed identity / Key Vault for credentials, per doc 02), and a
branch in `factory.get_provider` for `OLIVER_LLM_PROVIDER=azure_openai`. No agent,
scoring, coordinator, or Registrar code changes. Foundry Agent Service is a
distinct seam at the agent-runtime layer (threads/tools), not this model port.

## Remaining technical debt

1. **`LLMNarrator` bypasses the port** — it calls Azure OpenAI directly
   (`OLIVER_OPENAI_*`). Refactor it to depend on `LLMProvider` so all model access
   is unified and provider-agnostic. (Pre-existing; flagged here.)
2. **Agents not yet wired to a provider** — scoring is still deterministic by
   design this increment.
3. **Rubric `source_ref` is field-level** (`kind="field"`, locator = check id),
   not character spans. LLM/RAG agents will produce richer spans; rubric spans are
   a later refinement if needed.
4. **Transition chokepoint not yet done** — store+audit writes are still scattered
   (Increment 2).

## Recommended next increment

**Wire the LLM agents to the provider** (Increment 3), now that the contract and
port are ready: an `OLIVER_AGENTS=llm` path where each evaluator becomes
`prompt + AgentContext.model.complete(...)` returning `AgentResult` with typed
evidence and `scored_by="llm"`, with **per-dimension fallback** to the rubric
(mirroring the narrator's `llm-fallback`). Ollama is the development provider
behind the port. Validate with a rubric-vs-LLM shadow-diff on the seed set. The
transition chokepoint (Increment 2) is the recommended parallel hardening — it is
independent of the LLM work because agents are pure.
