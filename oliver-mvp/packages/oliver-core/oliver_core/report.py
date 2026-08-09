"""
Structured assessment report — the downloadable "complete record" artifact.

Renders a self-contained HTML document from a stored Submission + its Assessment.
This is the SAME record shown on the assessment page; the summary at the top of
the page and this report are two renderings of one source, so they can't diverge.

The renderer is a pure function with no framework dependency, so the same code
can later back Herald's outbound assessment email (Door A) unchanged.
"""

from __future__ import annotations

import html
from datetime import datetime

from oliver_core.schemas import Submission, GateDecision
from oliver_core.mock_assessor import stage_label


GATE_TEXT = {
    GateDecision.GATE_PASS: "Gate Pass",
    GateDecision.NO_GO_RECOMMENDED: "No-Go Recommended",
    GateDecision.COACHING_REJECT: "Coaching Reject",
}


def _e(text) -> str:
    return html.escape(str(text)) if text is not None else ""


def _ul(items: list[str]) -> str:
    return "".join(f"<li>{_e(i)}</li>" for i in items)


def _dimension_block(d) -> str:
    pct = round(d.value)
    strengths = (f'<p class="lbl lbl-str">Evidence</p><ul>{_ul(d.evidence)}</ul>'
                 if d.evidence else "")
    gaps = (f'<p class="lbl lbl-gap">Gaps</p><ul>{_ul(d.gaps)}</ul>'
            if d.gaps else "")
    return f"""
      <div class="dim">
        <div class="dim-head">
          <strong>{_e(d.dimension_label)}</strong>
          <span class="dim-meta"><b>{d.value} / 100</b> &middot; {_e(d.agent)}
            &middot; weight {d.weight}% &middot; confidence {round(d.confidence * 100)}%</span>
        </div>
        <div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div>
        <p class="dim-summary">{_e(d.summary)}</p>
        {strengths}
        {gaps}
      </div>"""


def render_report_html(sub: Submission) -> str:
    a = sub.assessment
    if a is None:
        raise ValueError("Submission has no assessment to render.")

    reject = a.verdict.gate_decision == GateDecision.COACHING_REJECT
    score_text = "&mdash;" if a.verdict.composite is None else f"{a.verdict.composite} / 100"
    gate_text = GATE_TEXT.get(a.verdict.gate_decision, str(a.verdict.gate_decision))
    stage_txt = stage_label(a.stage.assigned_stage)
    conf_text = (f"{round(a.verdict.composite_confidence * 100)}%"
                 if a.verdict.composite_confidence is not None else "&mdash;")
    assessed = a.assessed_at
    if isinstance(assessed, datetime):
        assessed = assessed.strftime("%Y-%m-%d %H:%M UTC")

    strengths = (f"""
      <section>
        <h2 class="h-str">&#9989; What's Working Well</h2>
        <div class="box box-green"><ul>{_ul(a.strengths)}</ul></div>
      </section>""" if a.strengths else "")

    coaching = (f"""
      <section>
        <h2 class="h-coach">&#128161; Coaching Recommendations</h2>
        {f'<p class="sub">{_e(a.coaching.message)}</p>' if a.coaching.message else ''}
        <div class="box box-violet"><ol>{_ul(a.coaching.actions)}</ol></div>
      </section>""" if a.coaching.actions else "")

    next_actions = (f"""
      <section>
        <h2 class="h-next">&#127919; Next Actions</h2>
        <div class="box box-amber"><ul>{_ul(a.next_actions)}</ul></div>
      </section>""" if a.next_actions else "")

    flags = ""
    if a.verdict.requires_human_review:
        flags += '<p class="flag">&#9888; Requires human review before the decision is final.</p>'
    if a.verdict.consistency_flags:
        flags += f'<p class="flag">&#9888; {_e("; ".join(a.verdict.consistency_flags))}</p>'

    dims = "".join(_dimension_block(d) for d in a.dimensions)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Oliver Assessment Record — {_e(sub.input.title)}</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#f4f6f7; color:#1f2933;
    font-family:'Segoe UI',Roboto,Arial,sans-serif; line-height:1.6; padding:24px 0 60px; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:0 22px; }}
  .banner {{ background:linear-gradient(135deg,#7c3aed,#4c1d95); color:#fff;
    border-radius:12px; padding:26px 28px; }}
  .eyebrow {{ font-size:11px; letter-spacing:.14em; text-transform:uppercase; opacity:.85; }}
  h1 {{ margin:8px 0 4px; font-size:23px; }}
  .scoreline {{ font-size:14px; color:#f3e8ff; }}
  .pills {{ margin-top:12px; display:flex; gap:8px; flex-wrap:wrap; }}
  .pill {{ background:rgba(255,255,255,.16); border-radius:20px; padding:4px 12px; font-size:12px; }}
  .meta {{ background:#fff; border:1px solid #e2e8ec; border-radius:10px; padding:14px 20px;
    margin:16px 0; font-size:13px; color:#5b6b78; display:grid;
    grid-template-columns:repeat(2,1fr); gap:5px 24px; }}
  .meta b {{ color:#1f2933; }}
  section {{ background:#fff; border:1px solid #e2e8ec; border-radius:10px;
    padding:20px 24px; margin:16px 0; }}
  h2 {{ font-size:16px; margin:0 0 10px; }}
  .h-exec, .h-coach, .h-dims {{ color:#5b21b6; }}
  .h-str {{ color:#15803d; }}
  .h-next {{ color:#b45309; }}
  p {{ margin:0 0 4px; }}
  .lede {{ font-size:14px; line-height:1.65; }}
  .sub {{ font-size:12.5px; color:#5b6b78; margin-bottom:10px; }}
  .box {{ border-radius:0 8px 8px 0; padding:12px 18px; }}
  .box ul, .box ol {{ margin:0; padding-left:20px; font-size:13.5px; line-height:1.6; }}
  .box li + li {{ margin-top:6px; }}
  .box-green {{ border-left:4px solid #16a34a; background:#f0fdf4; }}
  .box-violet {{ border-left:4px solid #7c3aed; background:#f7f2fd; }}
  .box-amber {{ border-left:4px solid #d97706; background:#fffbeb; }}
  .dim {{ border:1px solid #e2e8ec; border-radius:10px; margin:12px 0; padding:14px 16px; }}
  .dim-head {{ display:flex; justify-content:space-between; align-items:baseline;
    gap:12px; flex-wrap:wrap; }}
  .dim-head strong {{ color:#5b21b6; font-size:15px; }}
  .dim-meta {{ font-size:12px; color:#5b6b78; }}
  .dim-meta b {{ color:#1f2933; }}
  .bar {{ height:8px; background:#eef2f4; border-radius:6px; overflow:hidden; margin:10px 0; }}
  .bar-fill {{ height:100%; background:linear-gradient(90deg,#a78bfa,#5b21b6); }}
  .dim-summary {{ font-size:13px; color:#5b6b78; margin:0 0 8px; }}
  .lbl {{ font-size:11px; text-transform:uppercase; letter-spacing:.05em;
    font-weight:700; margin:8px 0 3px; }}
  .lbl-str {{ color:#15803d; }} .lbl-gap {{ color:#b45309; }}
  .dim ul {{ margin:0 0 6px; padding-left:20px; font-size:13px; line-height:1.55; }}
  .flag {{ color:#b45309; font-size:13px; margin-top:6px; }}
  .audit {{ font-size:11.5px; color:#8795a1; line-height:1.7; margin:18px 4px 0; }}
  .audit b {{ color:#5b21b6; }}
  @media(max-width:640px){{ .meta {{ grid-template-columns:1fr; }} }}
</style></head>
<body>
  <div class="wrap">

    <div class="banner">
      <div class="eyebrow">Oliver &middot; AI Pilot Stage-Gate Assessment &middot; Complete Record</div>
      <h1>{_e(sub.input.title)}</h1>
      <div class="scoreline">Stage: {stage_txt} &middot; Overall Score: {score_text}
        &middot; Rating: {_e(a.rating)}</div>
      <div class="pills">
        <span class="pill">Recommendation: {gate_text}</span>
        <span class="pill">Confidence: {conf_text}</span>
        <span class="pill">Lifecycle: {_e(a.stage.lifecycle_state)}</span>
      </div>
    </div>

    <div class="meta">
      <div><b>Submission ID:</b> {_e(str(sub.id)[:8])}</div>
      <div><b>Assessed:</b> {_e(assessed)}</div>
      <div><b>Assigned stage:</b> {_e(a.stage.assigned_stage)}</div>
      <div><b>Position:</b> {_e(a.position)}</div>
    </div>

    <section>
      <h2 class="h-exec">&#128203; Executive Summary</h2>
      <p class="lede">{_e(a.executive_summary)}</p>
    </section>

    {strengths}
    {coaching}
    {next_actions}

    <section>
      <h2 class="h-dims">Dimension-by-Dimension Assessment</h2>
      <p class="sub">Five canonical dimensions, stage-adaptive weights. Every score carries its
        supporting evidence &mdash; no evidence, no score.</p>
      {dims}
      {flags}
      <p class="sub" style="margin-top:12px;font-style:italic;">{_e(a.stage.rationale)}</p>
    </section>

    <div class="audit">
      <b>Record &amp; audit</b><br>
      Model: {_e(a.verdict.model_version)} &middot; Weights: {_e(a.verdict.weight_set_version)}
      &middot; Lowest-confidence dimension: {_e(a.verdict.lowest_confidence_dimension or "—")}<br>
      Generated by Oliver on {_e(assessed)}. Value figures are projections, not measured results.
      Oliver keeps a human in the loop &mdash; it suggests; a person decides.
      This document is a rendering of the audited assessment record.
    </div>

  </div>
</body></html>"""
