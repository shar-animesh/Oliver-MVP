# ADR 0002 — LLM Evaluators via the Provider Abstraction (Increment 3)

Status: Accepted · Final pre-Azure iteration · Deterministic scoring engine unchanged

## Context

Increments 1–2 delivered the typed agent/evidence contract and a vendor-neutral
provider port (Ollama as the only adapter). This increment completes the LLM
migration: the five deterministic evaluators can now be scored by an LLM through
the provider port, with structured-JSON validation and automatic per-dimension
fallback, and the narrator is moved onto the same port. Azure OpenAI is not yet
available; Ollama is the temporary local development provider and remains fully
isolated behind the abstraction.

The load-bearing principle (doc 02) is unchanged: **the LLM judges; deterministic
math decides.** LLM output feeds the existing scoring engine; the gate stays
reproducible, explainable, and auditable.

## Final architecture

```
 Submission
     │
     ▼
 resolve_agents()  ── OLIVER_AGENTS=rubric (default) ─► rubric AGENTS ─┐
     │              ── OLIVER_AGENTS=llm + provider   ─► LLM agents ────┤
     │                                                                  │
     │            each LLM agent (per dimension):                       │
     │              build_messages(rubric) ─► LLMProvider.complete()    │
     │              ─► extract_json ─► LLMDimensionOutput.validate       │
     │              ─► AgentResult(scored_by="llm")                      │
     │              └─ on ANY failure ─► deterministic evaluator         │
     │                                   AgentResult(scored_by=          │
     │                                   "llm-fallback")                 │
     ▼                                                                   ▼
 consolidate() ──►  run_scoring_engine()   [DETERMINISTIC — UNCHANGED]
     │              (completeness floor · weighted composite · gate · HITL)
     ▼
 Assessment (+ provenance when LLM-scored)
     │
     ▼
 generate_narrative(provider)  ── OLIVER_NARRATIVE=template (default) ─► TemplateNarrator
                                ── OLIVER_NARRATIVE=llm ─► LLMNarrator.complete() via port
                                   └─ on failure ─► template (generated_by="llm-fallback")

 Provider selection (the only vendor-aware seam):
   get_provider()  ─ OLIVER_LLM_PROVIDER = none (default) | ollama | [azure_openai…]
                     └─ lazily imports the chosen adapter; port names no vendor
```

Nothing in `resolve_agents`, the evaluators, `consolidate`, the scoring engine,
the narrator, `shadow`, or a future Registrar imports or names a concrete
provider — verified by source scan and subprocess import tests.

## Design decisions

1. **Provider injected at composition, not via AgentContext.** `AgentContext`
   stays submission-only (unchanged). The coordinator resolves the provider via
   the factory and binds it into each LLM agent (`make_llm_agent(provider, …)`).
   Rationale: the provider is a *capability wired at composition*, not request
   data; this keeps the context frozen and minimal while agents stay pure w.r.t.
   persistence.
2. **Prompts built from the rubric.** `prompts.py` holds the rubric as declarative
   data (per dimension: criteria id + description + weight, summing to 100),
   transcribed from the deterministic checks, and renders it into vendor-neutral
   `Message`s. No new evaluation logic is invented; the LLM scores the *same*
   weighted criteria the deterministic evaluator enforces.
3. **Structured JSON → Pydantic → AgentResult.** `LLMDimensionOutput` (extra keys
   ignored; `value` 0–100; `confidence` 0–1; required fields enforced) validates
   every response *before* it enters the system, then maps into the existing
   `AgentResult`/`Evidence`/`SourceRef` (evidence grounded as
   `source_ref.kind="submission_span"`). Contracts are unchanged.
4. **Fallback is the deterministic evaluator itself.** The same function used in
   rubric mode is the fallback and the prompt's source of truth — one source of
   truth, no divergence. Failure taxonomy: call error (`ProviderError`),
   unparseable/invalid JSON (`ValueError`, incl. `JSONDecodeError`), schema
   violation (`ValidationError`), plus a documented safety-net for any unexpected
   error so one dimension can never crash a whole assessment. Fallback is marked
   `scored_by="llm-fallback"`.
5. **Provenance without vendor coupling.** The port exposes a vendor-neutral
   `model` property; the coordinator records run-level
   `AssessmentProvenance{provider, model, prompt_version}` (additive, optional) on
   the Assessment when LLM evaluators scored the run. Per-dimension provenance is
   `DimensionScore.scored_by`; narrator provenance is
   `AssessmentNarrative.generated_by`. `AgentResult` and the evidence contracts are
   untouched.
6. **Narrator on the same port.** `LLMNarrator` now depends on `LLMProvider`
   (removing the direct Azure-OpenAI/urllib coupling — the debt flagged in ADR
   0001). `generate_narrative` is now `async`; it reuses the coordinator's provider
   when passed, else resolves its own, and degrades to the template on any failure.

## Provider abstraction (recap + delta)

Port: `LLMProvider{ name, model, async complete(messages, *, options) }` with
vendor-neutral `Message` / `CompletionOptions{temperature, max_tokens, json_mode}`
/ `Completion{text, model, prompt_tokens, completion_tokens}` and `ProviderError`.
Delta this increment: added the `model` property (for provenance). Selection is
`get_provider()` (config-driven, lazy adapter import). The Ollama adapter maps
`json_mode` → Ollama's `format:"json"` and uses an injected transport for tests.

## Prompt architecture

`PROMPT_VERSION = "assess-prompt/1.0.0"`. One system template (role, evidence-
mandatory rule, strict JSON-only schema, weighting instruction) + a per-dimension
user message listing the weighted criteria and the submission fields. Bump
`PROMPT_VERSION` on any change; it is captured in provenance so every score is
attributable to a prompt revision.

## Agent workflow

`resolve_agents()` → (agents, mode, provider). `rubric` by default; `llm` only when
`OLIVER_AGENTS=llm` **and** a provider is configured (otherwise it degrades to
rubric — safe by construction). LLM agents fan out exactly like rubric agents
(`asyncio.gather`), so a Durable orchestrator hosts either set unchanged.

## Files changed

New: `prompts.py`, `llm_evaluator.py`, `shadow.py`; tests `test_prompts.py`,
`test_llm_evaluator.py`, `test_llm_coordinator.py`, `tests/conftest.py`.
Modified: `schemas.py` (+`AssessmentProvenance`, +optional `Assessment.provenance`),
`providers/base.py` & `providers/ollama.py` (+`model`), `mock_assessor.py`
(evaluator registry, `build_llm_agents`, `resolve_agents`, provenance, async
narrator call), `narrative.py` (`LLMNarrator` on the port; `generate_narrative`
async), `tests/test_providers.py` (stub gains `model`).
Unchanged: scoring engine, `consolidate` math, audit, store, `report.py`, frontend,
`AgentContext`, `AgentResult`, `Evidence`, `SourceRef`.

## Configuration

| Variable | Values | Default | Purpose |
|---|---|---|---|
| `OLIVER_AGENTS` | `rubric` \| `llm` | `rubric` | Evaluator mode |
| `OLIVER_LLM_PROVIDER` | `none` \| `ollama` | `none` | Provider selection |
| `OLIVER_OLLAMA_BASE_URL` | URL | `http://localhost:11434` | Ollama endpoint |
| `OLIVER_OLLAMA_MODEL` | model id | `llama3.1` | Ollama model |
| `OLIVER_NARRATIVE` | `template` \| `llm` | `template` | Narrator mode |
| `OLIVER_NARRATIVE_MAX_TOKENS` | int | `2500` | Narrator token budget |

LLM scoring requires **both** `OLIVER_AGENTS=llm` and `OLIVER_LLM_PROVIDER=ollama`.

## Ollama setup

1. Install Ollama and pull a model: `ollama pull llama3.1` (a JSON-capable
   instruct model is recommended).
2. Ensure the server is running (`http://localhost:11434`).
3. `pip install httpx` in the runtime env (the adapter imports it lazily).
4. Export `OLIVER_LLM_PROVIDER=ollama`, `OLIVER_AGENTS=llm` (and optionally
   `OLIVER_NARRATIVE=llm`), then run an assessment. Validate with `shadow_compare`.

## Azure OpenAI migration guide

1. Add `providers/azure_openai.py` implementing `LLMProvider` (chat-completions →
   `Completion`; `json_mode` → `response_format={"type":"json_object"}`;
   credentials via managed identity / Key Vault per doc 02; `model` = deployment).
2. Add an `azure_openai` branch to `factory.get_provider` (lazy import).
3. Set `OLIVER_LLM_PROVIDER=azure_openai`. **No** change to evaluators, prompts,
   coordinator, scoring, narrator, or Registrar. Foundry Agent Service is a
   separate seam at the agent-runtime layer, not this model port.
4. Run `shadow_compare` on the corpus (Ollama vs Azure, and rubric vs LLM) before
   cutover.

## Test report

101 tests pass — 93 `oliver-core`, 8 `backend`.
- Prompts: version present; rubric covers all 5 dimensions; weights sum 100;
  messages carry criteria + submission; JSON-only instruction present.
- LLM evaluator: JSON extraction (plain / fenced / prose / garbage / non-object);
  Pydantic validation (valid + extra-ignored; missing/out-of-range → raise);
  typed-evidence mapping; success (`llm`) and fallback on provider-failure /
  bad-JSON / invalid-schema (`llm-fallback`).
- Coordinator/e2e: default deterministic; llm-without-provider degrades; llm with
  provider selects LLM; e2e llm sets provenance; e2e failure degrades per
  dimension yet still produces a valid gate; default sets no provenance.
- Shadow: runs and reports deltas + gate agreement; reports full fallback.
- Narrator: default template; llm uses provider; llm degrades on failure.
- Provider abstraction: port conformance; factory selection; Ollama request/response
  via injected transport; a second provider drops in with no consumer change.
- Isolation: importing the LLM stack does not load the Ollama module.

## Regression evidence

The 39 pre-existing core tests pass unchanged. Determinism test asserts identical
scoring projections across runs in the default path. The default assessment path
(rubric evaluators, template narrator, no provider) is byte-for-byte unchanged and
sets no provenance — backward compatibility preserved end to end (backend API tests
green).

## Known limitations

- **LLM scoring is non-deterministic** (even at temperature 0). This is why the
  scoring engine stays deterministic and why `shadow_compare` exists — validate
  before trusting, and monitor drift.
- **Prompt rubric is a transcription** of the deterministic checks, kept in sync by
  convention. A shared declarative rubric consumed by both paths would remove the
  duplication (see roadmap).
- **Evidence source spans are coarse** — the LLM returns a quoted excerpt as the
  locator, not character offsets.
- **Real-provider shadow/quality runs need a running Ollama** and are manual; CI
  covers the pipeline with stubs.

## Remaining technical debt

- Transition chokepoint (Increment 2) still not built — store/audit writes remain
  scattered; independent of this work.
- Prompt-rubric duplication (above).
- No token/latency telemetry emitted yet (provenance carries model/prompt only).

## Recommended roadmap after Azure OpenAI access

1. Implement `azure_openai` adapter + factory branch; managed identity + Key Vault.
2. Shadow-run the corpus (rubric vs LLM; Ollama vs Azure); tune prompts against the
   diff; set an acceptance bar (gate-agreement %, max per-dimension delta).
3. Cut over a cohort at a time (doc 02), keeping fallback on.
4. Derive the prompt rubric from a single declarative source shared with the
   deterministic checks (kill the transcription).
5. Add token/latency/quality telemetry keyed by `prompt_version` + `model`.
6. Then: embeddings/dedup (Scout/Connector), and the transition chokepoint.
