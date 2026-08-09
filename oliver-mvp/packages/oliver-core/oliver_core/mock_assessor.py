"""
Mock assessment pipeline — rubric-based evaluators + canonical scoring engine.

The mock agents use a deterministic evidence-presence rubric: each dimension
defines structural checks that inspect whether specific pieces of evidence
exist in the submission text.  Every score is traceable to detected (or absent)
evidence.  No score depends on domain keywords or content hashing.

The canonical scoring engine (weight-set/3.1.0, completeness pre-gate, ≥70 gate,
confidence routing) is production logic and is NOT mocked.

When real agents are connected (Azure AI Foundry), replace the mock_* functions.
The scoring engine stays unchanged.
"""

from __future__ import annotations

import asyncio
import os
import re
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import dataclass
from typing import Awaitable, Callable

from oliver_core.schemas import (
    Assessment, AgentResult, AssessmentProvenance, CoachingNote, DIStage, DimensionScore,
    Evidence, GateDecision, LifecycleState, SourceRef, StageAssignment,
    SubmissionCreate, VerdictResult,
)
from oliver_core import weights
from oliver_core.llm_evaluator import make_llm_agent
from oliver_core.prompts import PROMPT_VERSION
from oliver_core.providers import get_provider


# ═══════════════════════════════════════════════════════════════════════════
# CANONICAL SCORING DATA — from weight-set/3.1.0 and scoring-model/3.1.0
# (production logic — do not modify for mock purposes)
# ═══════════════════════════════════════════════════════════════════════════

WEIGHT_SET_VERSION = "weight-set/3.1.0"
MODEL_VERSION = "scoring-model/3.1.0"

DIMENSIONS = (
    ("ideaCompleteness",     "Idea Completeness",          "DocGuard"),
    ("ideaQuality",          "Idea Quality",               "IdeaPulse"),
    ("strategicValue",       "Strategic / Business Value",  "ValuePulse"),
    ("technicalFeasibility", "Technical Feasibility",       "TechScope"),
    ("executionReadiness",   "Execution Readiness",         "PathFinder"),
)

DIMENSION_KEYS = tuple(d[0] for d in DIMENSIONS)

# Weights are now versioned DATA (oliver_core/weights.py + data/weight-set-*.json).
# This alias exposes the DEFAULT weight-set's weights for backward-compatible imports;
# the scoring engine resolves the ACTIVE (or an explicitly passed) weight-set at runtime.
WEIGHTS_BY_STAGE: dict[str, dict[str, int]] = weights.default_weight_set().weights

COMPLETENESS_FLOOR = 30
GATE_THRESHOLD = 70
CONFIDENCE_FLOOR = 0.6
IRREVERSIBLE_STAGES = {"DI5"}
STAGE_ORDER = ("DI1", "DI2", "DI3", "DI4", "DI5")


def _stage_below(stage: str) -> str:
    idx = STAGE_ORDER.index(stage)
    return STAGE_ORDER[max(0, idx - 1)]


# ═══════════════════════════════════════════════════════════════════════════
# CANONICAL SCORING ENGINE — pure function, matches CSS engine.py
# (production logic — do not modify for mock purposes)
# ═══════════════════════════════════════════════════════════════════════════

def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def score_composite(scores: dict[str, int], weights: dict[str, int]) -> int:
    weighted = sum(Decimal(scores[k]) * Decimal(weights[k]) for k in DIMENSION_KEYS)
    return _round_half_up(weighted / Decimal(100))


def score_confidence(confidences: dict[str, float], weights: dict[str, int]) -> float:
    weighted = sum(Decimal(str(confidences[k])) * Decimal(weights[k]) for k in DIMENSION_KEYS)
    return float((weighted / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def run_scoring_engine(
    scores: dict[str, int],
    confidences: dict[str, float],
    stage: str,
    weight_set: "weights.WeightSet | None" = None,
) -> dict:
    ws = weight_set or weights.active_weight_set()
    stage_weights = ws.weights_for(stage)
    lowest_conf_dim = min(DIMENSION_KEYS, key=lambda k: (confidences[k], DIMENSION_KEYS.index(k)))

    if scores["ideaCompleteness"] < COMPLETENESS_FLOOR:
        return {
            "composite": None,
            "gate_decision": GateDecision.COACHING_REJECT,
            "assigned_stage": None,
            "composite_confidence": None,
            "lowest_confidence_dimension": lowest_conf_dim,
            "requires_human_review": False,
        }

    composite = score_composite(scores, stage_weights)
    confidence = score_confidence(confidences, stage_weights)

    if composite >= GATE_THRESHOLD:
        gate = GateDecision.GATE_PASS
        assigned = stage
    else:
        gate = GateDecision.NO_GO_RECOMMENDED
        assigned = _stage_below(stage)

    requires_human = (
        gate is GateDecision.NO_GO_RECOMMENDED
        or confidence < CONFIDENCE_FLOOR
        or assigned in IRREVERSIBLE_STAGES
    )

    return {
        "composite": composite,
        "gate_decision": gate,
        "assigned_stage": assigned,
        "composite_confidence": confidence,
        "lowest_confidence_dimension": lowest_conf_dim,
        "requires_human_review": requires_human,
    }


# ═══════════════════════════════════════════════════════════════════════════
# RUBRIC-BASED MOCK EVALUATORS
#
# Design principle: each check inspects whether a specific piece of
# EVIDENCE exists in the submission.  The rubric scores evidence presence,
# not domain relevance.  A well-documented coffee bot will outscore an
# undocumented turbine idea — because at this layer the question is
# "did the submitter provide what's needed for evaluation?"
#
# Every evidence string cites actual submission content or notes its absence.
# Replace these with real LLM agent calls when Azure AI Foundry is ready.
# ═══════════════════════════════════════════════════════════════════════════

# Pattern: digits followed by a unit-like token (currency, %, time)
_QUANT_RE = re.compile(
    r'\d[\d,.]*\s*'
    r'(%|EUR|USD|GBP|€|\$|£|million|mio|billion|bn'
    r'|hours?|days?|weeks?|months?|years?|mins?'
    r'|k\b|K\b|pct|percent)',
    re.IGNORECASE,
)


def _has_quantity(text: str) -> str | None:
    """Return the first quantified claim found, or None."""
    m = _QUANT_RE.search(text)
    return m.group(0).strip() if m else None


# ═══════════════════════════════════════════════════════════════════════════
# LINGUISTIC INFERENCE DETECTORS
#
# Oliver assesses ideas as they arrive by EMAIL — natural prose, not structured
# forms.  These detectors infer each dimension's evidence from the SHAPE of the
# language (role phrases, named systems, method verbs, capacity mentions), not
# from a fixed list of domain terms.  Every detector returns the actual matched
# text so the evidence stays traceable to what the submitter wrote.
#
# A populated structured field is one signal; the same fact expressed in prose
# is an equally valid signal.  The evaluators stack both.
# ═══════════════════════════════════════════════════════════════════════════

# Generic organizational role tokens — no company- or domain-specific names.
# Sponsor: an authority is named or referenced with backing/ownership framing.
# Bare role words ("manager", "lead") are NOT enough on their own — they often
# appear as the subject of the problem, not as a project sponsor.  We require
# either (a) a senior title, (b) a title qualified by "of <Area>" or a name, or
# (c) explicit backing language ("on behalf of", "sponsored by").
_SENIOR_TITLE = (r'(?:VP|SVP|EVP|CEO|CTO|CFO|COO|CIO|CISO|President'
                 r'|Vice[- ]President|Chief|Head\s+of)')
_SPONSOR_RE = re.compile(
    r'\b' + _SENIOR_TITLE + r'\b(?:\s+of\s+[A-Za-z][\w&/ -]{2,40})?'          # VP / Head of Procurement / Chief ...
    r'|\b(?:Director|Manager|Lead|Officer|Owner)\s+of\s+[A-Z][\w&/ -]{2,40}'   # Director of Operations
    r'|on behalf of\s+[A-Za-z][\w .-]{2,40}'                                    # on behalf of our VP / Maria
    r'|sponsored by\s+[A-Za-z][\w .-]{2,40}'
    r'|backed by\s+[A-Za-z][\w .-]{2,40}'
    r'|reporting to\s+[A-Za-z][\w .-]{2,40}'
    r'|\bour\s+' + _SENIOR_TITLE + r'\b',                                       # our VP / our Chief
    re.IGNORECASE,
)

# Data source: a NAMED or SPECIFIC source.  Vague references ("lots of data",
# "our data") are the absence of a usable source, not evidence of one — so they
# must not match.  Ordered most-specific first so the citation quotes the source
# phrase itself, not a greedy run.  The bare "<Name> <data-noun>" pattern is
# constrained to at most two capitalized tokens so it can't span a whole clause.
_DATA_NOUN = (r'(?:system|database|data ?base|historian|logs?|records?|sensors?'
              r'|dataset|warehouse|repository|spreadsheet|API|feed|telemetry)')
_DATA_RE = re.compile(
    r'\b(?:data|logs?|records?|readings?|telemetry)\s+from\s+(?:our\s+|the\s+)?[A-Z][\w -]{2,30}'   # data from PI System
    r'|\b(?:from|in|stored in)\s+(?:our\s+|the\s+)?[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?\s+' + _DATA_NOUN   # in PI System / in the SAP historian
    + r'|\bwe (?:already )?(?:collect|store|log|capture|record)\s+\w+\s+(?:data|logs?|readings?|telemetry)\b'   # we already collect vibration data
    + r'|\b(?:our|the)\s+[A-Z][A-Za-z0-9]+\s+' + _DATA_NOUN   # our Salesforce database (named)
    + r'|\b[A-Z][A-Za-z0-9]{2,}\s+' + _DATA_NOUN + r'\b'   # PI historian / SAP records (single proper noun + noun)
    + r'|\b(?:historical|past|previous|existing|archived)\s+(?:[\w-]+\s+){0,3}'
      r'(?:proposals?|records?|data|documents?|outcomes|reports?|contracts?|invoices?|tickets?|emails?|logs?|drawings?)\b'  # historical project proposals
    + r'|\bdata sources?\s*[:\-]\s*[\w ,.&-]{3,80}',   # explicit "Data sources: ..." label in prose
    re.IGNORECASE,
)

# Strong approach evidence: a verb+object phrase or a named technique — preferred
# for citation over bare action verbs, so the quoted sentence is the actual approach.
_APPROACH_STRONG_RE = re.compile(
    r'\b(?:using|use|uses|build|builds|building|built on|based on|powered by|train|trains|training'
    r'|develop|develops|deploy|deploys|implement|implements|apply|applies|leverage|leverages'
    r'|integrate|integrates|integrated with|exploring)\s+(?:an?\s+|the\s+)?[\w .-]{3,40}'
    r'|\b(?:machine learning|deep learning|neural network|LLMs?|large language models?|generative AI'
    r'|GenAI|foundation models?|GPT[-\w]*|copilot|chatbot|RAG|retrieval[- ]augmented'
    r'|AI[- ](?:powered|based|driven|assisted)|Power (?:Platform|Automate|Apps)|Azure OpenAI'
    r'|anomaly detection|time[- ]series|computer vision)\b',
    re.IGNORECASE,
)

# Technical approach: method/intent verbs and technique nouns.
_APPROACH_RE = re.compile(
    r'\b(?:using|use|uses|build|builds|building|built on|based on|powered by|train|trains|training'
    r'|develop|develops|deploy|deploys|implement|implements|apply|applies|leverage|leverages'
    r'|integrate|integrates|integrated with)\s+(?:an?\s+|the\s+)?[\w .-]{3,40}'
    r'|\b(?:predict|detect|classify|forecast|automat\w+|recommend|extract|summari[sz]e|cluster|rank|score|flag|identif\w+|optimi[sz]e)\b'
    r'|\b(?:machine learning|deep learning|neural network|LLMs?|large language models?|generative AI'
    r'|GenAI|foundation models?|GPT[-\w]*|copilot|chatbot|RAG|retrieval[- ]augmented'
    r'|AI[- ](?:powered|based|driven|assisted)|Power (?:Platform|Automate|Apps)|Azure OpenAI'
    r'|NLP|natural language|anomaly detection|time[- ]series|computer vision|OCR|regression|models?|algorithms?)\b'
    r'|\bwe could\s+[\w .-]{3,40}',
    re.IGNORECASE,
)

# Execution readiness: team capacity, readiness phrasing, timeline.
_EXEC_RE = re.compile(
    r'\bteam of\s+\w+'
    r'|\b\d+\s+(?:people|persons?|engineers?|developers?|analysts?|FTEs?|resources?|members?)\b'
    r'|\b(?:ready to|prepared to|able to|we can|we have|I(?:\'ve| have) got)\s+[\w .-]{3,40}'
    r'|\bnext\s+(?:quarter|month|sprint|week|year)\b'
    r'|\b(?:prototype|pilot|proof[- ]of[- ]concept|PoC|kick[- ]?off|roll ?out)\b'
    r'|\bwithin\s+\d+\s+(?:weeks?|months?|quarters?)\b',
    re.IGNORECASE,
)


def _detect(rx: re.Pattern, text: str, max_len: int = 110) -> str | None:
    """
    Run a detector and return the CONTAINING PHRASE for citation, or None.
    Citing the sentence around the match (not the bare matched word) keeps the
    evidence meaningful to a human reader.
    """
    m = rx.search(text)
    if not m:
        return None
    # expand to sentence-ish boundaries around the match
    start, end = m.start(), m.end()
    cands = []
    for delim, off in ((". ", 2), ("! ", 2), ("\n", 1)):
        i = text.rfind(delim, 0, start)
        if i >= 0:
            cands.append(i + off)
    left = max(cands) if cands else max(0, start - 40)
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i >= 0]
    right = min(right_candidates) + 1 if right_candidates else min(len(text), end + 60)
    phrase = " ".join(text[left:right].split()).strip(" .")
    if len(phrase) > max_len:
        # keep the matched text inside the window
        m_in = phrase.lower().find(m.group(0).strip().lower()[:20])
        s = max(0, (m_in if m_in >= 0 else 0) - 25)
        if s and phrase[s - 1] != " ":
            s = phrase.find(" ", s) + 1          # snap forward to a word boundary
        phrase = ("…" if s else "") + phrase[s:s + max_len].rsplit(" ", 1)[0] + "…"
    return phrase


def _excerpt(text: str, max_len: int = 60) -> str:
    """Short excerpt for evidence citations."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    points: int        # 0 if not passed, max_points if passed
    max_points: int
    evidence: str      # always present — explains why it passed or failed


def _all_text(sub: SubmissionCreate) -> str:
    """Concatenate all text fields for cross-field searches."""
    return " ".join(filter(None, [
        sub.problem_statement, sub.proposed_approach, sub.expected_value,
        sub.data_sources, sub.description,
    ]))


# ── Combined signal resolvers: structured field OR inferred from prose ────
#
# Each returns (found: bool, citation: str).  A populated structured field
# wins (it's the most explicit signal); otherwise the prose detector runs
# over the full submission text.  The citation always quotes real content.

def _resolve_sponsor(sub: SubmissionCreate) -> tuple[bool, str]:
    if sub.sponsor.strip():
        return True, _excerpt(sub.sponsor)
    hit = _detect(_SPONSOR_RE, _all_text(sub))
    if hit:
        return True, f'inferred from text — "{hit}"'
    return False, "no sponsor or authority referenced"


def _resolve_data(sub: SubmissionCreate) -> tuple[bool, str]:
    if sub.data_sources.strip():
        return True, _excerpt(sub.data_sources)
    hit = _detect(_DATA_RE, _all_text(sub))
    if hit:
        return True, f'inferred from text — "{hit}"'
    return False, "no data source identified"


def _resolve_approach(sub: SubmissionCreate) -> tuple[bool, str]:
    if sub.proposed_approach.strip():
        return True, _excerpt(sub.proposed_approach)
    strong = _detect(_APPROACH_STRONG_RE, _all_text(sub))
    if strong:
        return True, f'inferred from text — "{strong}"' 
    hit = _detect(_APPROACH_RE, _all_text(sub))
    if hit:
        return True, f'inferred from text — "{hit}"'
    return False, "no technical approach described"


def _resolve_value(sub: SubmissionCreate) -> tuple[bool, str]:
    if sub.expected_value.strip():
        return True, _excerpt(sub.expected_value)
    # Value in prose = a quantified benefit somewhere in the text
    q = _has_quantity(_all_text(sub))
    if q:
        return True, f'quantified benefit inferred from text — "{q}"'
    return False, "no value or benefit stated"


def _resolve_execution(sub: SubmissionCreate) -> tuple[bool, str]:
    if sub.team_size is not None and sub.team_size > 0:
        return True, f"team size {sub.team_size}"
    hit = _detect(_EXEC_RE, _all_text(sub))
    if hit:
        return True, f'inferred from text — "{hit}"'
    return False, "no team or execution capacity indicated"


# ── DocGuard: Idea Completeness ──────────────────────────────────────────

async def mock_doc_guard(sub: SubmissionCreate) -> tuple[int, float, str, list[str], list[str]]:
    """
    RUBRIC: Does the submission contain the required fields for evaluation?
    A substantive problem statement alone should pass the completeness floor (30),
    because in the email-first workflow the email body IS the submission.
    Each additional field adds evidence.
    """
    checks: list[CheckResult] = []

    # 1. Problem present (always true from validation, but checks substance)
    checks.append(CheckResult("problem_present", True, 15, 15,
        f"Problem statement provided ({len(sub.problem_statement)} chars)"))

    # 2. Problem substantive — long enough to contain a real description
    ok = len(sub.problem_statement) >= 50
    checks.append(CheckResult("problem_substantive", ok, 15 if ok else 0, 15,
        f"Problem statement {'is' if ok else 'is not'} substantive "
        f"({len(sub.problem_statement)} chars, threshold: 50)"))

    # 3. Problem detailed — multiple clauses, suggests cause and effect
    ok = len(sub.problem_statement) >= 120
    checks.append(CheckResult("problem_detailed", ok, 10 if ok else 0, 10,
        f"Problem detail: {len(sub.problem_statement)} chars "
        f"{'(extended detail present)' if ok else '(below 120-char depth threshold)'}"))

    # 4. Approach present — field OR inferred from prose
    ap_ok, ap_cite = _resolve_approach(sub)
    checks.append(CheckResult("approach_provided", ap_ok, 12 if ap_ok else 0, 12,
        f"Proposed approach: {ap_cite if ap_ok else 'not provided'}"))

    # 5. Approach substantive — field length OR a prose approach was inferred
    ok = len(sub.proposed_approach.strip()) >= 40 or (ap_ok and not sub.proposed_approach.strip())
    checks.append(CheckResult("approach_substantive", ok, 8 if ok else 0, 8,
        f"Approach depth: "
        + (f"{len(sub.proposed_approach)} chars (substantive)" if len(sub.proposed_approach.strip()) >= 40
           else "described in narrative" if ok else f"{len(sub.proposed_approach)} chars (threshold: 40)")))

    # 6. Value present — field OR quantified benefit in prose
    v_ok, v_cite = _resolve_value(sub)
    checks.append(CheckResult("value_stated", v_ok, 12 if v_ok else 0, 12,
        f"Expected value: {v_cite if v_ok else 'not provided'}"))

    # 7. Data source present — field OR named system in prose
    d_ok, d_cite = _resolve_data(sub)
    checks.append(CheckResult("data_sources_named", d_ok, 10 if d_ok else 0, 10,
        f"Data sources: {d_cite}"))

    # 8. Sponsor present — field OR authority referenced in prose
    s_ok, s_cite = _resolve_sponsor(sub)
    checks.append(CheckResult("sponsor_named", s_ok, 8 if s_ok else 0, 8,
        f"Sponsor: {s_cite}"))

    # 9. Execution capacity — team field OR capacity referenced in prose
    e_ok, e_cite = _resolve_execution(sub)
    checks.append(CheckResult("team_specified", e_ok, 5 if e_ok else 0, 5,
        f"Team / capacity: {e_cite}"))

    # 10. Additional context
    ok = len(sub.description.strip()) >= 15
    checks.append(CheckResult("context_provided", ok, 5 if ok else 0, 5,
        f"Additional context: {'provided' if ok else 'not provided'} "
        f"({len(sub.description)} chars)"))

    return _finalize_checks(checks, "Completeness assessed from field presence and depth.")


# ── IdeaPulse: Idea Quality ──────────────────────────────────────────────

async def mock_idea_pulse(sub: SubmissionCreate) -> tuple[int, float, str, list[str], list[str]]:
    """
    RUBRIC: Is the problem real, specific, and worth solving?
    Scans ALL available text for quality signals — not just dedicated fields.
    """
    checks: list[CheckResult] = []
    all_text = _all_text(sub)

    # 1. Problem specificity (length as proxy — short statements are usually vague)
    ok = len(sub.problem_statement) >= 70
    checks.append(CheckResult("problem_specific", ok, 15 if ok else 0, 15,
        f"Problem specificity: {len(sub.problem_statement)} chars "
        f"{'(sufficient detail for evaluation)' if ok else '(too brief to identify a concrete process)'}"))

    # 2. Impact quantified — numbers in ANY text field
    q = _has_quantity(all_text)
    ok = q is not None
    checks.append(CheckResult("impact_quantified", ok, 20 if ok else 0, 20,
        f"Quantified impact: found — \"{q}\"" if ok
        else "Quantified impact: no numeric impact claim found in submission"))

    # 3. Consequence articulation — problem has enough structure for cause-effect
    sentences = [s.strip() for s in re.split(r'[.!?;]', sub.problem_statement) if len(s.strip()) > 8]
    ok = len(sentences) >= 2
    checks.append(CheckResult("consequence_stated", ok, 15 if ok else 0, 15,
        f"Consequence: {len(sentences)} clause(s) in problem statement "
        f"{'(cause and effect expressed)' if ok else '(single clause — consequence unclear)'}"))

    # 4. Stakeholders identifiable — sponsor/team via field OR prose
    s_ok, _ = _resolve_sponsor(sub)
    e_ok, _ = _resolve_execution(sub)
    ok = s_ok or e_ok
    checks.append(CheckResult("stakeholders_clear", ok, 10 if ok else 0, 10,
        f"Stakeholders: {'identified (sponsor or team, from field or narrative)' if ok else 'not identified'}"))

    # 5. Approach is concrete — field OR inferred from prose
    ap_ok, ap_cite = _resolve_approach(sub)
    ok = len(sub.proposed_approach.strip()) >= 20 or (ap_ok and not sub.proposed_approach.strip())
    checks.append(CheckResult("approach_concrete", ok, 15 if ok else 0, 15,
        f"Concrete approach: "
        + (f"described ({len(sub.proposed_approach)} chars)" if len(sub.proposed_approach.strip()) >= 20
           else ap_cite if ok else "not provided or too brief to evaluate")))

    # 6. Coherence — problem present AND approach (field or prose) present
    ok = len(sub.problem_statement) >= 30 and ap_ok
    checks.append(CheckResult("problem_approach_fit", ok, 10 if ok else 0, 10,
        "Problem–approach coherence: both present (approach from field or narrative)" if ok
        else "Coherence: cannot be assessed — no approach found"))

    # 7. Depth — count distinct evidence types present (fields OR inferred)
    depth_signals = sum([
        ap_ok,                               # approach
        _resolve_value(sub)[0],              # value
        _resolve_data(sub)[0],               # data
        len(sub.description.strip()) >= 10,  # explicit extra context
    ])
    ok = depth_signals >= 2
    checks.append(CheckResult("depth_of_detail", ok, 15 if ok else 0, 15,
        f"Supporting detail: {depth_signals} evidence type(s) present "
        f"{'(adequate depth)' if ok else '(insufficient)'}"))

    return _finalize_checks(checks, "Idea quality assessed from structural evidence.")


# ── ValuePulse: Strategic / Business Value ───────────────────────────────

async def mock_value_pulse(sub: SubmissionCreate) -> tuple[int, float, str, list[str], list[str]]:
    """
    RUBRIC: Is there a credible value claim?
    Scans expected_value AND problem_statement for quantification signals.
    """
    checks: list[CheckResult] = []
    all_text = _all_text(sub)

    # 1. Value present — field OR quantified benefit inferred from prose
    v_ok, v_cite = _resolve_value(sub)
    checks.append(CheckResult("value_explicit", v_ok, 20 if v_ok else 0, 20,
        f"Value claim: {v_cite if v_ok else 'not provided'}"))

    # 2. Financial impact quantified (anywhere in submission)
    q = _has_quantity(_all_text(sub))
    ok = q is not None
    checks.append(CheckResult("financial_quantified", ok, 20 if ok else 0, 20,
        f"Financial quantification: found — \"{q}\"" if ok
        else "Financial quantification: no quantified claim found"))

    # 3. Efficiency/productivity gain — value field substance OR quantified prose benefit
    ok = len(sub.expected_value.strip()) >= 25 or (v_ok and not sub.expected_value.strip())
    checks.append(CheckResult("efficiency_claimed", ok, 15 if ok else 0, 15,
        f"Efficiency description: "
        + (f"{len(sub.expected_value)} chars (substantive)" if len(sub.expected_value.strip()) >= 25
           else "expressed in narrative" if ok else "insufficient")))

    # 4. Scale indicated — quantification anywhere suggests measurable impact
    has_scale = _has_quantity(all_text) is not None and len(all_text) >= 80
    checks.append(CheckResult("scale_indicated", has_scale, 15 if has_scale else 0, 15,
        "Scale: quantified indicators found across submission" if has_scale
        else "Scale: impact magnitude not clear from submission"))

    # 5. Value description substantive — value field OR quantified benefit in prose
    ok = len(sub.expected_value.strip()) >= 40 or (v_ok and _has_quantity(_all_text(sub)) is not None)
    checks.append(CheckResult("value_substantive", ok, 15 if ok else 0, 15,
        f"Value depth: "
        + (f"{len(sub.expected_value)} chars (substantive)" if len(sub.expected_value.strip()) >= 40
           else "quantified benefit present in narrative" if ok else "below 40-char threshold")))

    # 6. Baseline referenced — problem quantifies current state
    ok = _has_quantity(sub.problem_statement) is not None
    checks.append(CheckResult("baseline_referenced", ok, 15 if ok else 0, 15,
        "Baseline: problem statement includes quantified current state" if ok
        else "Baseline: no quantified current state in problem statement"))

    return _finalize_checks(checks, "Strategic value assessed from value claims and quantification.")


# ── TechScope: Technical Feasibility ─────────────────────────────────────

async def mock_tech_scope(sub: SubmissionCreate) -> tuple[int, float, str, list[str], list[str]]:
    """
    RUBRIC: Is it buildable?
    Checks approach detail, data identification, and integration surface.
    """
    checks: list[CheckResult] = []

    # 1. Technical approach specified — field OR inferred from prose
    ap_ok, ap_cite = _resolve_approach(sub)
    checks.append(CheckResult("approach_specified", ap_ok, 20 if ap_ok else 0, 20,
        f"Technical approach: {ap_cite if ap_ok else 'not provided'}"))

    # 2. Approach has implementation detail — field length only (prose rarely detailed)
    ok = len(sub.proposed_approach.strip()) >= 60
    checks.append(CheckResult("approach_detailed", ok, 15 if ok else 0, 15,
        f"Approach depth: {len(sub.proposed_approach)} chars "
        f"{'(includes implementation detail)' if ok else '(threshold: 60)'}"))

    # 3. Data sources named — field OR named system in prose
    d_ok, d_cite = _resolve_data(sub)
    checks.append(CheckResult("data_sources_named", d_ok, 20 if d_ok else 0, 20,
        f"Data sources: {d_cite if d_ok else 'not identified — data readiness cannot be assessed'}"))

    # 4. Data source description substantive — field length OR a prose data source inferred
    ok = len(sub.data_sources.strip()) >= 15 or (d_ok and not sub.data_sources.strip())
    checks.append(CheckResult("data_substantive", ok, 15 if ok else 0, 15,
        f"Data detail: "
        + (f"{len(sub.data_sources)} chars (substantive)" if len(sub.data_sources.strip()) >= 15
           else "source named in narrative" if ok else "insufficient")))

    # 5. Integration surface identifiable — data or approach present (field or prose)
    ok = d_ok or ap_ok
    checks.append(CheckResult("integration_surface", ok, 15 if ok else 0, 15,
        "Integration: identifiable from approach or data evidence" if ok
        else "Integration: not determinable"))

    # 6. Supporting technical context — explicit description OR both approach+data inferred
    has_ctx = (len(sub.description.strip()) >= 15 and (ap_ok or d_ok)) or (ap_ok and d_ok)
    checks.append(CheckResult("context_supports_tech", has_ctx, 15 if has_ctx else 0, 15,
        "Technical context: detail supports assessment" if has_ctx
        else "Technical context: no supporting detail provided"))

    return _finalize_checks(checks, "Technical feasibility assessed from approach and data evidence.")


# ── PathFinder: Execution Readiness ──────────────────────────────────────

async def mock_path_finder(sub: SubmissionCreate) -> tuple[int, float, str, list[str], list[str]]:
    """
    RUBRIC: Can this be executed?
    Checks sponsor, team capacity, scope, and supporting context.
    """
    checks: list[CheckResult] = []

    # 1. Sponsor identified
    # 1. Sponsor identified — field OR authority referenced in prose
    s_ok, s_cite = _resolve_sponsor(sub)
    checks.append(CheckResult("sponsor_identified", s_ok, 25 if s_ok else 0, 25,
        f"Sponsor: {s_cite if s_ok else 'not identified — execution accountability unclear'}"))

    # 2. Sponsor is specific — field ≥5 chars OR a role/name was inferred
    ok = len(sub.sponsor.strip()) >= 5 or (s_ok and not sub.sponsor.strip())
    checks.append(CheckResult("sponsor_substantive", ok, 10 if ok else 0, 10,
        "Sponsor detail: name or role identified" if ok
        else "Sponsor detail: too brief or missing"))

    # 3. Team adequate — field ≥2 OR capacity referenced in prose
    e_ok, e_cite = _resolve_execution(sub)
    team_ok = (sub.team_size is not None and sub.team_size >= 2) or \
              (e_ok and sub.team_size is None)
    checks.append(CheckResult("team_adequate", team_ok, 20 if team_ok else 0, 20,
        f"Team capacity: {sub.team_size} people (adequate)" if (sub.team_size and sub.team_size >= 2)
        else f"Team capacity: {e_cite}" if team_ok
        else f"Team: {sub.team_size or 'not specified'} (minimum 2 required)"))

    # 4. Team/execution info present — field OR any execution signal in prose
    ok = (sub.team_size is not None and sub.team_size > 0) or e_ok
    checks.append(CheckResult("team_present", ok, 10 if ok else 0, 10,
        "Execution capacity: indicated (field or narrative)" if ok
        else "Execution capacity: not specified"))

    # 5. Scope appears bounded
    ok = 30 <= len(sub.problem_statement) <= 300
    checks.append(CheckResult("scope_manageable", ok, 15 if ok else 0, 15,
        f"Scope: {len(sub.problem_statement)} chars (appears bounded)" if ok
        else f"Scope: {len(sub.problem_statement)} chars (may be unbounded)"))

    # 6. Execution context — count distinct execution signals (fields OR inferred)
    ctx_signals = sum([
        s_ok,                                  # sponsor (field or prose)
        e_ok,                                  # execution/team (field or prose)
        len(sub.description.strip()) >= 10,    # explicit extra context
    ])
    ok = ctx_signals >= 2
    checks.append(CheckResult("execution_context", ok, 20 if ok else 0, 20,
        f"Execution context: {ctx_signals} signal(s) present"
        + (" (adequate)" if ok else " (insufficient)")))

    return _finalize_checks(checks, "Execution readiness assessed from sponsor, team, and scope evidence.")


# ── Shared finalization ──────────────────────────────────────────────────

def _finalize_checks(
    checks: list[CheckResult],
    summary_base: str,
) -> tuple[int, float, str, list[Evidence], list[str]]:
    """
    Convert check results into the agent return tuple.

    Score = sum of earned points (rubric guarantees 0–100 range).
    Confidence = fraction of checks that passed (more evidence → higher confidence).
    Evidence = typed items for passed checks (claim = the existing explanation,
               byte-identical to before; source_ref points at the grounding check).
    Gaps = list of failed-check explanations (explaining what's missing).
    """
    score = sum(c.points for c in checks)
    passed_count = sum(1 for c in checks if c.passed)
    confidence = round(min(0.95, 0.3 + 0.65 * (passed_count / len(checks))), 2)

    evidence = [
        Evidence(claim=c.evidence, source_ref=SourceRef(kind="field", locator=c.check_id))
        for c in checks if c.passed
    ]
    gaps = [c.evidence for c in checks if not c.passed]

    # Build a summary that reflects the actual result
    pct = passed_count / len(checks)
    if pct >= 0.8:
        summary = f"{summary_base} {passed_count}/{len(checks)} checks passed — strong evidence."
    elif pct >= 0.5:
        summary = f"{summary_base} {passed_count}/{len(checks)} checks passed — partial evidence, gaps remain."
    else:
        summary = f"{summary_base} {passed_count}/{len(checks)} checks passed — insufficient evidence for a confident assessment."

    return score, confidence, summary, evidence, gaps


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY SYNTHESIS — the human-facing narrative (executive summary, strengths,
# next actions, rating, position). Derived from the same scoring pass so the
# summary report and the dimension detail can never disagree.
#
# In the mock these are templated from the structural signals. When real agents
# (IdeaCoach / Azure AI Foundry) are connected, they populate the SAME fields
# with richer prose — the frontend and downloadable report are unchanged.
# ═══════════════════════════════════════════════════════════════════════════

STAGE_NAMES = {
    "DI1": "Concept", "DI2": "Feasibility", "DI3": "Prototype",
    "DI4": "Pilot", "DI5": "Scale",
}


def stage_label(stage) -> str:
    """'DI1' -> 'DI1 — Concept' (accepts a DIStage or a str)."""
    code = stage.value if hasattr(stage, "value") else str(stage)
    name = STAGE_NAMES.get(code, "")
    return f"{code} — {name}" if name else code


def rating_for(composite: int | None) -> str:
    if composite is None:
        return "Incomplete"
    if composite >= 85:
        return "Excellent"
    if composite >= 70:
        return "Strong"
    if composite >= 55:
        return "Developing"
    if composite >= 40:
        return "Early"
    return "Nascent"


def _short(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _next_stage(stage_code: str) -> str:
    i = STAGE_ORDER.index(stage_code)
    return STAGE_ORDER[min(len(STAGE_ORDER) - 1, i + 1)]


def _build_summary(
    verdict: VerdictResult,
    stage_assign: StageAssignment,
    dimension_scores: list[DimensionScore],
) -> dict:
    reject = verdict.gate_decision == GateDecision.COACHING_REJECT
    is_pass = verdict.gate_decision == GateDecision.GATE_PASS
    stage_code = stage_assign.assigned_stage.value
    stage_txt = stage_label(stage_assign.assigned_stage)

    scored = [d for d in dimension_scores if d.dimension != "ideaCompleteness"]
    weakest = sorted(scored, key=lambda d: d.value)[:2]
    weak_labels = " and ".join(d.dimension_label.lower() for d in weakest) or "the weaker dimensions"
    strongest = max(dimension_scores, key=lambda d: d.value)

    rating = rating_for(verdict.composite)

    # ── Position (banner line) ──
    if reject:
        position = "Below the completeness floor — add the missing detail below and resubmit."
    elif is_pass:
        position = (f"{stage_code} cleared — ready to progress; "
                    f"keep strengthening {weak_labels} before the next gate.")
    else:
        position = f"Mid {stage_code} — a faster path opens once {weak_labels} are addressed."

    # ── Executive summary ──
    if reject:
        exec_summary = (
            "This submission doesn't yet carry enough detail to assess against the gate. "
            "The fastest way forward is to expand the problem statement and add the missing "
            "context listed below — once the essentials are present, Oliver can score the idea properly."
        )
    else:
        gate_clause = ("clears the gate, so the idea can progress"
                       if is_pass else
                       f"sits just below the gate (\u2265{GATE_THRESHOLD}), so a No-Go is recommended for now")
        lever = weakest[0].dimension_label.lower() if weakest else "the weakest dimension"
        exec_summary = (
            f"At {stage_txt}, the clearest strength of this idea is "
            f"{strongest.dimension_label.lower()} ({strongest.value}/100). "
            f"The composite of {verdict.composite}/100 {gate_clause}. "
            f"The areas holding it back are {weak_labels} — closing these would move the score the most. "
            f"To advance with confidence, focus first on {lever}."
        )

    # ── Strengths ("What's Working Well") — strongest dimensions, evidence-cited ──
    def _user_cite(d) -> str:
        # prefer evidence that quotes the submitter's own words; never surface
        # rubric internals (char counts / thresholds) as a "strength"
        for e in d.evidence:
            if "\u201c" in e or '\"' in e or "inferred from text" in e:
                return _short(e, 120)
        for e in d.evidence:
            if "chars" not in e and "threshold" not in e:
                return _short(e, 120)
        return ""

    strengths: list[str] = []
    for d in sorted([d for d in dimension_scores if d.value >= 60],
                    key=lambda d: d.value, reverse=True)[:3]:
        cite = _user_cite(d)
        strengths.append(f"{d.dimension_label} ({d.value}/100)" + (f" — {cite}" if cite else "") + ".")
    if not strengths:
        strengths.append(
            f"{strongest.dimension_label} is the strongest area so far "
            f"({strongest.value}/100) — a foothold to build on."
        )

    # ── Next actions — crisp, forward-framed, ending in a resubmit/prepare step ──
    next_actions: list[str] = []
    if reject:
        for d in dimension_scores:
            if d.gaps:
                next_actions.append(_short(d.gaps[0]))
            if len(next_actions) >= 3:
                break
        next_actions = next_actions[:3]
        next_actions.append("Add the missing detail above, then resubmit for re-assessment.")
    else:
        for d in weakest:
            gap = _short(d.gaps[0]) if d.gaps else ""
            next_actions.append(f"Strengthen {d.dimension_label.lower()}" + (f" — {gap}" if gap else ""))
        if is_pass:
            next_actions.append(f"Prepare the evidence for the {_next_stage(stage_code)} gate review.")
        else:
            next_actions.append("Address the items above, then resubmit for re-assessment.")

    return {
        "executive_summary": exec_summary,
        "strengths": strengths,
        "next_actions": next_actions,
        "rating": rating,
        "position": position,
    }


# ═══════════════════════════════════════════════════════════════════════════
# AGENT LAYER — the swap point for real Foundry agents / Durable activities
#
# Each Agent is (AgentContext) -> AgentResult. The mock evaluators above are
# unchanged (they still return tuples); here they are wrapped into Agents that
# carry their dimension identity. To connect a REAL agent (LLM/Foundry), replace
# its entry in AGENTS with a callable that takes the AgentContext and returns an
# AgentResult — the coordinator, scoring, and downstream are untouched.
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AgentContext:
    """
    Input to an agent. Minimal by decision — the submission only.

    Capability seams (a model client for LLM agents, a retriever for RAG, a tool
    registry, long-term memory) are added here ADDITIVELY when their consumers
    land, so no capability is populated speculatively today. Agents depend on this
    context, never on how they are triggered or where anything is hosted.
    """
    submission: SubmissionCreate


Agent = Callable[["AgentContext"], Awaitable[AgentResult]]


def _make_agent(evaluator, agent: str, dimension: str, dimension_label: str) -> Agent:
    async def _agent(ctx: AgentContext) -> AgentResult:
        value, conf, summary, evidence, gaps = await evaluator(ctx.submission)
        return AgentResult(
            agent=agent, dimension=dimension, dimension_label=dimension_label,
            value=value, confidence=conf, summary=summary,
            evidence=evidence, gaps=gaps, scored_by="rubric",
        )
    _agent.__name__ = f"{agent.lower()}_agent"
    return _agent


# The fan-out set. This list is what a Durable orchestrator will drive as
# parallel activities. Order is not relied upon — consolidation maps by dimension.
# One registry of (deterministic evaluator, agent, dimension, label). Used to
# build BOTH the rubric AGENTS and the LLM agents — the deterministic evaluator is
# the single source of truth and the LLM fallback.
_EVALUATOR_REGISTRY: tuple[tuple, ...] = (
    (mock_doc_guard,   "DocGuard",   "ideaCompleteness",     "Idea Completeness"),
    (mock_idea_pulse,  "IdeaPulse",  "ideaQuality",          "Idea Quality"),
    (mock_value_pulse, "ValuePulse", "strategicValue",       "Strategic / Business Value"),
    (mock_tech_scope,  "TechScope",  "technicalFeasibility", "Technical Feasibility"),
    (mock_path_finder, "PathFinder", "executionReadiness",   "Execution Readiness"),
)

# The deterministic fan-out set (default; unchanged behaviour). A Durable
# orchestrator drives this as parallel activities; order is not relied upon.
AGENTS: list[Agent] = [_make_agent(ev, a, d, lbl) for (ev, a, d, lbl) in _EVALUATOR_REGISTRY]


def build_llm_agents(provider) -> list[Agent]:
    """Build one LLM agent per dimension, bound to `provider`, each with its
    deterministic evaluator as the fallback. Provider is the port — vendor-agnostic."""
    return [
        make_llm_agent(provider, ev, a, d, lbl)
        for (ev, a, d, lbl) in _EVALUATOR_REGISTRY
    ]


def resolve_agents(provider=None):
    """
    Select the agent set for a run: (agents, mode, provider).

    Deterministic by default. LLM agents are used only when OLIVER_AGENTS=llm AND a
    provider is configured (via the factory); otherwise the run degrades gracefully
    to the deterministic agents. The coordinator depends on the LLMProvider port and
    the factory only — it never learns which vendor backs the provider.
    """
    mode = os.getenv("OLIVER_AGENTS", "rubric").strip().lower()
    if mode == "llm":
        provider = provider if provider is not None else get_provider()
        if provider is not None:
            return build_llm_agents(provider), "llm", provider
    return list(AGENTS), "rubric", None


# ═══════════════════════════════════════════════════════════════════════════
# CONSOLIDATION — the Canonical Scoring Service boundary (Verdict + StageMaster)
#
# Pure function: (agent scores, stage) -> (dimension scores, verdict, stage).
# No I/O; maps onto a single Durable activity or a call to the CSS service.
# ═══════════════════════════════════════════════════════════════════════════

ASSESSMENT_STAGE = "DI1"   # fixed for now; assessing at the submission's real stage is a later iteration


def consolidate(
    agent_scores: list[AgentResult], stage: str = ASSESSMENT_STAGE,
    weight_set: "weights.WeightSet | None" = None,
) -> tuple[list[DimensionScore], VerdictResult, StageAssignment]:
    ws = weight_set or weights.active_weight_set()
    stage_weights = ws.weights_for(stage)
    by_key = {a.dimension: a for a in agent_scores}
    scores_map = {k: by_key[k].value for k in DIMENSION_KEYS}
    conf_map = {k: by_key[k].confidence for k in DIMENSION_KEYS}

    dimension_scores = [
        DimensionScore(
            agent=by_key[k].agent, dimension=k, dimension_label=by_key[k].dimension_label,
            value=by_key[k].value, confidence=by_key[k].confidence, weight=stage_weights[k],
            summary=by_key[k].summary, evidence_detail=by_key[k].evidence,
            gaps=by_key[k].gaps, scored_by=by_key[k].scored_by,
        )
        for k in DIMENSION_KEYS
    ]

    # ── Canonical scoring engine (unchanged) ──
    engine_result = run_scoring_engine(scores_map, conf_map, stage, weight_set=ws)

    flags = []
    values = list(scores_map.values())
    if max(values) - min(values) > 40:
        flags.append("Large spread across dimensions — review recommended")

    verdict = VerdictResult(
        composite=engine_result["composite"],
        gate_decision=engine_result["gate_decision"],
        assigned_stage=(DIStage(engine_result["assigned_stage"])
                        if engine_result["assigned_stage"] else None),
        composite_confidence=engine_result["composite_confidence"],
        lowest_confidence_dimension=engine_result["lowest_confidence_dimension"],
        requires_human_review=engine_result["requires_human_review"],
        consistency_flags=flags,
        model_version=ws.model_version,
        weight_set_version=ws.version,
    )

    # ── StageMaster ──
    if verdict.gate_decision == GateDecision.COACHING_REJECT:
        state = LifecycleState.STALLED
        stage_val = DIStage(stage)
        rationale = (f"Completeness score {scores_map['ideaCompleteness']}/100 is below "
                     f"the floor ({COMPLETENESS_FLOOR}). Coaching rejection applied.")
    elif verdict.gate_decision == GateDecision.GATE_PASS:
        state = LifecycleState.ACTIVE
        stage_val = verdict.assigned_stage
        rationale = (f"Composite {verdict.composite}/100 passes the gate (\u2265{GATE_THRESHOLD}). "
                     f"Assigned {stage_val.value}.")
    else:
        state = LifecycleState.ASSESSED
        stage_val = verdict.assigned_stage or DIStage.DI1
        rationale = (f"Composite {verdict.composite}/100 below gate threshold ({GATE_THRESHOLD}). "
                     f"No-Go recommended; assigned {stage_val.value}.")

    if verdict.requires_human_review:
        rationale += " Requires human review before decision is final."

    stage_assign = StageAssignment(
        assigned_stage=stage_val, lifecycle_state=state, rationale=rationale,
    )
    return dimension_scores, verdict, stage_assign


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — thin composition: fan-out agents -> consolidate -> coach -> summarize
#
# Contains no I/O of its own (the agents do the I/O), so it maps directly onto a
# Durable Functions orchestrator, which forbids I/O in the orchestrator body.
# ═══════════════════════════════════════════════════════════════════════════

async def assess_submission(sub: SubmissionCreate) -> Assessment:
    """
    Assessment pipeline (mock agents behind the real seam):
      1. fan-out the agent registry in parallel (Durable activities later)
      2. consolidate — canonical scoring engine + StageMaster (the CSS boundary)
      3. IdeaCoach coaching + summary synthesis from the consolidated result
    """
    agents, agent_mode, provider = resolve_agents()
    ctx = AgentContext(submission=sub)
    agent_scores = list(await asyncio.gather(*(agent(ctx) for agent in agents)))

    dimension_scores, verdict, stage = consolidate(agent_scores, sub.current_stage.value)

    scores_map = {d.dimension: d.value for d in dimension_scores}
    dim_gaps = {d.dimension: d.gaps for d in dimension_scores}
    all_gaps = [g for d in dimension_scores for g in d.gaps]

    coaching = _build_coaching(verdict, scores_map, dim_gaps, all_gaps)
    summary = _build_summary(verdict, stage, dimension_scores)

    assessment = Assessment(
        dimensions=dimension_scores,
        verdict=verdict,
        stage=stage,
        coaching=coaching,
        executive_summary=summary["executive_summary"],
        strengths=summary["strengths"],
        next_actions=summary["next_actions"],
        rating=summary["rating"],
        position=summary["position"],
    )

    # ── LLM provenance (only when LLM evaluators scored the run) ──
    if agent_mode == "llm" and provider is not None:
        assessment.provenance = AssessmentProvenance(
            provider=provider.name, model=provider.model, prompt_version=PROMPT_VERSION,
        )

    # ── Narrative layer: narrate the consolidated record (template default; LLM
    # when configured, via the same provider port). Lift the narrated summary/
    # actions into the legacy fields so every existing consumer improves without a
    # contract change. ──
    from oliver_core import narrative as _narrative
    n = await _narrative.generate_narrative(sub, assessment, provider=provider)
    assessment.narrative = n
    if n.executive_summary:
        assessment.executive_summary = n.executive_summary
    if n.recommended_next_steps:
        assessment.next_actions = n.recommended_next_steps
    return assessment




_COACH_ACTIONS = [
    ("Value claim", "State the expected value with a number — e.g. hours saved per week, % effort reduction, or EUR impact."),
    ("Financial quantification", "Quantify at least one benefit (a %, a EUR figure, or a time saving) so the business case is measurable."),
    ("Efficiency description", "Describe the efficiency gain concretely: who saves time, on what task, and roughly how much."),
    ("Baseline", "Quantify today's baseline in the problem statement (e.g. hours spent, error rate, cost) so improvement is measurable."),
    ("Sponsor", "Name a sponsor or accountable owner (e.g. 'sponsored by the Head of Operations') so execution has an anchor."),
    ("Team", "Indicate who would run this — even 'a team of 3 with one data engineer' establishes capacity."),
    ("Technical approach", "Describe how it would work in one or two sentences — the technique, and what it consumes and produces."),
    ("Data sources", "Name the data this would use (system, dataset, or document set) so feasibility can be assessed."),
    ("Additional context", "Add brief context: what exists today, what's been tried, and any constraints."),
    ("Scale", "Indicate the scale of impact — how many people, cases, or hours per week are affected."),
    ("Approach depth", "Expand the technical approach — a sentence on the technique and a sentence on inputs/outputs is enough."),
    ("Sponsor detail", "Name a sponsor or accountable owner (e.g. 'sponsored by the Head of Operations') so execution has an anchor."),
    ("Execution", "Describe execution readiness: who runs it, at what capacity, and the first milestone."),
    ("Problem", "Sharpen the problem statement with specifics: who is affected, how often, and what it costs today."),
    ("Scope", "Bound the scope explicitly — one department, one process, or one document type for the pilot."),
    ("Integration", "Note what the solution must integrate with (email, ERP, SharePoint, etc.)."),
    ("Concrete approach", "Describe the approach concretely — the technique and what it consumes and produces."),
    ("Supporting detail", "Add one or two supporting facts: prior attempts, available data, or early results."),
]


def _map_actions(gaps: list[str]) -> list[str]:
    """Map gaps to actionable coaching and de-duplicate while preserving order."""
    seen, out = set(), []
    for g in gaps:
        a = _coaching_phrase(g)
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _coaching_phrase(gap: str) -> str:
    for prefix, action in _COACH_ACTIONS:
        if gap.startswith(prefix):
            return action
    return gap

def _build_coaching(
    verdict: VerdictResult,
    scores: dict[str, int],
    dim_gaps: dict[str, list[str]],
    all_gaps: list[str],
) -> CoachingNote:
    """
    Generate coaching that targets the actual weak dimensions.
    Instead of a generic message, identify the weakest areas and
    surface their specific gaps as action items.
    """
    if verdict.gate_decision == GateDecision.COACHING_REJECT:
        return CoachingNote(
            message="The submission does not meet the completeness threshold. "
                    "Please provide more detail in the areas listed below and resubmit.",
            actions=_map_actions(all_gaps[:6])[:5],
            next_gate_hint="Resubmit when these gaps are addressed.",
        )

    # Find the two weakest dimensions (excluding completeness, which has its own gate)
    scored_dims = [(k, scores[k]) for k in DIMENSION_KEYS if k != "ideaCompleteness"]
    scored_dims.sort(key=lambda x: x[1])
    weakest = scored_dims[:2]

    dim_labels = dict((d[0], d[1]) for d in DIMENSIONS)

    if verdict.gate_decision == GateDecision.GATE_PASS:
        weak_names = [dim_labels[k] for k, _ in weakest if scores[k] < 80]
        if weak_names:
            areas = " and ".join(weak_names)
            msg = (f"Strong submission — clears the gate. "
                   f"Consider strengthening {areas} before the next review stage.")
        else:
            msg = "Strong submission — clears the gate with solid evidence across all dimensions."

        # Actions: top gaps from the weakest passing dimensions
        actions = []
        for dim_key, _ in weakest:
            actions.extend(dim_gaps.get(dim_key, [])[:2])
        if not actions:
            actions = ["Confirm data access with IT", "Schedule kick-off with sponsor"]

        return CoachingNote(message=msg, actions=_map_actions(actions[:6])[:4])

    else:  # NO_GO_RECOMMENDED
        weak_names = [dim_labels[k] for k, _ in weakest]
        areas = " and ".join(weak_names)
        msg = (f"The submission has addressable gaps, primarily in {areas}. "
               f"Closing these would materially improve the composite score.")

        actions = []
        for dim_key, _ in weakest:
            actions.extend(dim_gaps.get(dim_key, [])[:3])
        if not actions:
            actions = all_gaps[:4]

        return CoachingNote(
            message=msg,
            actions=_map_actions(actions[:6])[:5],
            next_gate_hint="Revisit when the gaps above are addressed.",
        )
