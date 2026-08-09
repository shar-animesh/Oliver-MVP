# Mock Evaluator Rubric

This document explains how the mock evaluators score submissions. It exists so a
reviewer can understand exactly why any score was assigned, and so whoever
replaces the mock with real Azure AI Foundry agents knows what contract to preserve.

## Design principle

The mock scores **evidence presence**, not semantic merit.

A real LLM agent judges whether an idea is *good*. The mock cannot — and must not
pretend to. Instead, each dimension asks: *did the submitter provide the evidence
needed to evaluate this dimension?* A well-documented coffee-ordering bot will
therefore out-score a one-sentence turbine idea, because at this layer the
question is completeness of evidence, not importance of the domain.

This is deliberate. Any attempt to make the mock "know" that turbines matter more
than coffee would require hardcoded domain keywords — a content-blind toy model
dressed up as judgment. The rubric avoids that trap: it only inspects structure.

## How scoring works

Each dimension defines a set of **checks**. Every check:

1. Inspects a specific structural property of the submission (field present? length
   above a threshold? a number detected in the text?).
2. Awards its full points or zero — no partial credit within a check.
3. Emits an **evidence string** when it passes (citing the actual content found)
   or a **gap string** when it fails (explaining what is missing).

Points per dimension sum to 100. The dimension score is the sum of awarded points.
Confidence is `0.3 + 0.65 × (checks_passed / total_checks)`, capped at 0.95 — more
evidence means higher confidence.

The five dimension scores then flow **unchanged** into the canonical scoring engine
(`weight-set/3.1.0`), which applies stage-adaptive weights, the completeness
pre-gate (<30 → COACHING_REJECT), the ≥70 gate, and confidence-based HITL routing.
The engine is production logic and is not part of the mock.

## The checks

### DocGuard — Idea Completeness (are the required fields present?)

| Check | Points | Passes when |
|---|---|---|
| problem_present | 15 | Problem statement exists (always, given schema validation) |
| problem_substantive | 15 | Problem ≥ 50 chars |
| problem_detailed | 10 | Problem ≥ 120 chars |
| approach_provided | 12 | Proposed approach is non-empty |
| approach_substantive | 8 | Approach ≥ 40 chars |
| value_stated | 12 | Expected value is non-empty |
| data_sources_named | 10 | Data sources non-empty |
| sponsor_named | 8 | Sponsor non-empty |
| team_specified | 5 | Team size > 0 |
| context_provided | 5 | Description ≥ 15 chars |

A substantive problem statement alone earns 30 — exactly at the completeness floor,
which reflects the email-first reality that the email body *is* the submission.

### IdeaPulse — Idea Quality (is the problem real, specific, worth solving?)

| Check | Points | Passes when |
|---|---|---|
| problem_specific | 15 | Problem ≥ 70 chars (length as specificity proxy) |
| impact_quantified | 20 | A number+unit is detected anywhere in the submission |
| consequence_stated | 15 | Problem has ≥ 2 clauses (cause/effect structure) |
| stakeholders_clear | 10 | Sponsor or team present |
| approach_concrete | 15 | Approach ≥ 20 chars |
| problem_approach_fit | 10 | Both problem (≥30) and approach (≥10) present |
| depth_of_detail | 15 | ≥ 2 optional fields have substance |

### ValuePulse — Strategic / Business Value (is there a credible value claim?)

| Check | Points | Passes when |
|---|---|---|
| value_explicit | 20 | Expected value non-empty |
| financial_quantified | 20 | Number+unit in value field or problem statement |
| efficiency_claimed | 15 | Value ≥ 25 chars |
| scale_indicated | 15 | Quantification present and total text ≥ 80 chars |
| value_substantive | 15 | Value ≥ 40 chars |
| baseline_referenced | 15 | Problem statement contains a quantified current state |

### TechScope — Technical Feasibility (is it buildable?)

| Check | Points | Passes when |
|---|---|---|
| approach_specified | 20 | Approach non-empty |
| approach_detailed | 15 | Approach ≥ 60 chars |
| data_sources_named | 20 | Data sources non-empty |
| data_substantive | 15 | Data sources ≥ 15 chars |
| integration_surface | 15 | Data ≥ 10 chars OR approach ≥ 40 chars |
| context_supports_tech | 15 | Description ≥ 15 chars AND (approach or data present) |

### PathFinder — Execution Readiness (can this be executed?)

| Check | Points | Passes when |
|---|---|---|
| sponsor_identified | 25 | Sponsor non-empty |
| sponsor_substantive | 10 | Sponsor ≥ 5 chars |
| team_adequate | 20 | Team size ≥ 2 |
| team_present | 10 | Team size > 0 |
| scope_manageable | 15 | Problem 30–300 chars (bounded scope) |
| execution_context | 20 | ≥ 2 of {sponsor, description, data} have substance |

## Quantity detection

`impact_quantified`, `financial_quantified`, `scale_indicated`, and
`baseline_referenced` share one regex (`_QUANT_RE`) that matches a digit run
followed by a unit token: `%`, currency (`EUR`, `USD`, `€`, `$`, `£`, `k`/`K`),
magnitude words (`million`, `bn`), or time units (`hours`, `weeks`, `months`,
`years`). When it matches, the matched text is quoted verbatim in the evidence
string — so "found — 30%" always corresponds to a real "30%" in the submission.

## Natural-language inference (email-first)

Oliver assesses ideas **as they arrive by email** — natural prose, not tidy
forms. So each evaluator reads the *entire submission text* and infers a
dimension's evidence from the **shape of the language**, not from whether a
specific structured field was filled.

A populated structured field is the strongest signal and always wins. When the
field is empty, a prose detector runs over the full text. The same fact expressed
either way earns the same credit. Concretely, this email —

> "Hi, on behalf of our VP of Gas Services, our turbine fleet loses about 2M EUR
> a year to downtime. We could predict failures 48h ahead using anomaly detection
> on the vibration data we collect in PI System. I've got a team of four ready to
> prototype next quarter."

— scores ~95 with **every field empty**, because the evaluators infer the sponsor
("on behalf of our VP of Gas Services"), value ("2M EUR", "30%"), approach
("anomaly detection"), data source ("in PI System"), and execution capacity
("team of four") from the prose. The same idea as a bare one-liner scores ~5.

### What the detectors look for (structure, not domain terms)

| Dimension signal | Fires on | Deliberately does **not** fire on |
|---|---|---|
| **Sponsor** | Senior titles (VP, Chief, Head of X), "Director/Manager of <Area>", "on behalf of…", "sponsored by…", "our VP" | A bare "manager" that is the *subject of the problem* ("our manager wants…") |
| **Data source** | Named systems ("PI System", "SAP Ariba database"), "data from <Name>", "we collect <X> data" | Vague mentions ("lots of data", "our data") |
| **Approach** | Method verbs (predict, detect, classify, automate…), technique nouns (NLP, anomaly detection, model…), "using <X>" | A problem with no stated method |
| **Value** | A quantity + unit anywhere (%, EUR, hours, weeks…) | Prose with no numbers |
| **Execution** | "team of N", "N engineers", "ready to prototype", "next quarter", "PoC/pilot" | Aspiration with no capacity or timeline |

These are **domain-neutral**: they match linguistic patterns (role phrases,
proper-noun system names, method verbs, quantities, capacity mentions), never a
hardcoded list of Siemens systems or business terms. That keeps the mock honest —
it recognizes the *form* of evidence in any domain, and every inferred item is
quoted verbatim in the evidence string (prefixed "inferred from text — …") so a
reviewer can trace it to the exact words the submitter wrote.

### Why conservative matters

The detectors are tuned to under-claim rather than over-claim. A submission that
mentions "our team manager" or "we have lots of data" does **not** get a sponsor
or a data source inferred, because those are the *absence* of real evidence, not
its presence. False positives would erode the traceability guarantee, so the
detectors require specificity (a senior/qualified title, a named system) before
they fire.

## Replacing the mock with real agents

Each `mock_*` function returns a 5-tuple:

```
(score: int 0–100, confidence: float 0–1, summary: str,
 evidence: list[str], gaps: list[str])
```

To go live, replace the five `mock_*` functions with calls to the corresponding
Azure AI Foundry agents (DocGuard, IdeaPulse, ValuePulse, TechScope, PathFinder),
returning the same 5-tuple. The real agents will produce *semantic* scores and
evidence drawn from the submission — the planning-doc requirement of
"evidence-mandatory scoring." Everything downstream (the orchestrator, the
canonical engine, `_build_coaching`, the API contract, the frontend) stays
unchanged.
