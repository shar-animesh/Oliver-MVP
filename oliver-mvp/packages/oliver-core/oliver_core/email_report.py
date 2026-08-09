"""
Submitter-facing Herald email report — the historical Oliver assessment format.

One rendering of the assessment record for Door A: the email a submitter receives.
Email-safe by construction (nested tables, inline styles, web-safe fonts, no
flexbox/grid/JS) so it renders identically in Outlook and in a browser preview.
Renders from the same record as every other view; if the narrative block is
absent it degrades to the legacy summary fields.
"""

from __future__ import annotations

import html
from datetime import datetime

from oliver_core.schemas import GateDecision, Submission

V = {"violet": "#7c3aed", "violetD": "#4c1d95", "violetMid": "#5b21b6",
     "ink": "#1f2933", "muted": "#5b6b78", "line": "#e2e8ec",
     "green": "#15803d", "greenBar": "#16a34a", "greenTint": "#f0fdf4",
     "violetTint": "#f7f2fd", "amber": "#b45309", "amberBar": "#d97706",
     "amberTint": "#fffbeb", "blue": "#1d4ed8", "blueTint": "#eff6ff"}

GATE_TEXT = {GateDecision.GATE_PASS: "Gate Pass",
             GateDecision.NO_GO_RECOMMENDED: "No-Go Recommended",
             GateDecision.COACHING_REJECT: "Coaching Reject"}

STAGE_NAMES = {"DI1": "Concept", "DI2": "Pilot", "DI3": "Test",
               "DI4": "Implement", "DI5": "Scale"}


def _e(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def _stage_label(stage) -> str:
    code = stage.value if hasattr(stage, "value") else str(stage)
    name = STAGE_NAMES.get(code, "")
    return f"{code} \u2014 {name}" if name else code


def _section_h(emoji: str, title: str, color: str) -> str:
    return (f'<div style="font-size:16px;font-weight:700;color:{color};'
            f'margin:0 0 10px;">{emoji} {title}</div>')


def _accent_box(bar: str, tint: str, inner: str) -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;"><tr>'
            f'<td width="4" bgcolor="{bar}" style="width:4px;background:{bar};font-size:0;">&nbsp;</td>'
            f'<td bgcolor="{tint}" style="background:{tint};padding:14px 18px;">{inner}</td>'
            f'</tr></table>')


def _ul(items: list[str], numbered: bool = False) -> str:
    tag = "ol" if numbered else "ul"
    lis = "".join(f'<li style="margin:7px 0;">{_e(i)}</li>' for i in items)
    return (f'<{tag} style="margin:0;padding-left:20px;font-size:13.5px;'
            f'line-height:1.6;color:{V["ink"]};">{lis}</{tag}>')


def _row(td: str) -> str:
    return f'<tr><td style="padding:20px 28px 4px;">{td}</td></tr>'


def _guidance_block(label: str, text: str) -> str:
    if not text:
        return ""
    return (f'<div style="margin:12px 0;padding:13px 16px;background:#ffffff;'
            f'border:1px solid #d8e6f5;border-radius:8px;">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.06em;'
            f'text-transform:uppercase;color:{V["blue"]};margin:0 0 5px;">{_e(label)}</div>'
            f'<div style="font-size:13.5px;line-height:1.6;color:{V["ink"]};">{_e(text)}</div></div>')


def render_submitter_email(sub: Submission) -> str:
    """Render the submitter-facing assessment email (the Door-A experience)."""
    a = sub.assessment
    if a is None:
        raise ValueError("Submission has no assessment to render.")
    n = a.narrative  # may be None → degrade to legacy fields

    reject = a.verdict.gate_decision == GateDecision.COACHING_REJECT
    score_text = "\u2014" if a.verdict.composite is None else f"{a.verdict.composite} / 100"
    stage_txt = _stage_label(a.stage.assigned_stage)
    gate_txt = GATE_TEXT.get(a.verdict.gate_decision, "")
    assessed = a.assessed_at.strftime("%d %b %Y") if isinstance(a.assessed_at, datetime) else str(a.assessed_at)

    exec_summary = (n.executive_summary if n and n.executive_summary else a.executive_summary)
    working = (n.whats_working_well if n and n.whats_working_well else a.strengths)
    coach_msg = (n.coaching_message if n else a.coaching.message)
    coaching = (n.coaching_recommendations if n and n.coaching_recommendations else a.coaching.actions)
    steps = (n.recommended_next_steps if n and n.recommended_next_steps else a.next_actions)

    rows: list[str] = []

    # ── Executive Summary ──
    grounding = ""
    if n and n.evidence_basis.get("executive_summary"):
        items = " \u00b7 ".join(_e(x) for x in n.evidence_basis["executive_summary"][:3])
        grounding = (f'<p style="margin:8px 0 0;font-size:11px;color:#8795a1;">'
                     f'<b>Grounded in:</b> {items}</p>')
    rows.append(_row(
        _section_h("\U0001F4CB", "Executive Summary", V["violetMid"])
        + f'<p style="margin:0;font-size:14px;line-height:1.7;color:{V["ink"]};">{_e(exec_summary)}</p>'
        + grounding))

    # ── What's Working Well ──
    if working:
        rows.append(_row(
            _section_h("\u2705", "What's Working Well", V["green"])
            + _accent_box(V["greenBar"], V["greenTint"], _ul(working))))

    # ── Coaching Recommendations ──
    if coaching:
        sub_line = (f'<p style="margin:0 0 10px;font-size:12.5px;color:{V["muted"]};">{_e(coach_msg)}</p>'
                    if coach_msg else "")
        rows.append(_row(
            _section_h("\U0001F4A1", "Coaching Recommendations", V["violetMid"])
            + sub_line + _accent_box(V["violet"], V["violetTint"], _ul(coaching, numbered=True))))

    # ── AI Approach Guidance ──
    if n and (n.approach_guidance.problem_type or n.approach_guidance.recommended_approach):
        g = n.approach_guidance
        inner = (f'<p style="margin:0 0 4px;font-size:12.5px;color:{V["muted"]};">Below is AI technique '
                 f'coaching in plain language \u2014 focused on the quickest, safest way to prove value.</p>'
                 + _guidance_block("Problem type", g.problem_type)
                 + _guidance_block("Recommended approach", g.recommended_approach)
                 + _guidance_block("What to do first", g.what_to_do_first))
        rows.append(_row(
            _section_h("\U0001F916", "AI Approach Guidance", V["blue"])
            + f'<div style="background:{V["blueTint"]};border-radius:8px;padding:12px 16px;">{inner}</div>'))

    # ── Path to next gate ──
    if n and n.path_to_next_gate.milestones:
        p = n.path_to_next_gate
        inner = (f'<p style="margin:0 0 8px;font-size:13px;color:{V["ink"]};">'
                 f'<b>Target:</b> {_e(p.target_stage)} &nbsp;\u00b7&nbsp; '
                 f'<b>Typical timeline:</b> {_e(p.target_timeline)}</p>'
                 f'<p style="margin:0 0 6px;font-size:12.5px;color:{V["muted"]};">Key milestones required '
                 f'to pass the gate:</p>' + _ul(p.milestones, numbered=True))
        rows.append(_row(
            _section_h("\U0001F3AF", f"Path to {_e(p.target_stage.split(' ')[0])}", V["violetMid"])
            + _accent_box("#93c5fd", V["blueTint"], inner)))

    # ── Timeline guidance ──
    if n and (n.timeline_guidance.pace_note or n.timeline_guidance.risk_to_avoid):
        t = n.timeline_guidance
        def trow(k, v):
            return ("" if not v else
                    f'<tr><td style="padding:9px 12px;font-size:12px;font-weight:700;color:{V["muted"]};'
                    f'white-space:nowrap;vertical-align:top;border-bottom:1px solid {V["line"]};">{_e(k)}</td>'
                    f'<td style="padding:9px 12px;font-size:13px;line-height:1.55;color:{V["ink"]};'
                    f'border-bottom:1px solid {V["line"]};">{_e(v)}</td></tr>')
        inner = (f'<p style="margin:0 0 10px;font-size:13.5px;line-height:1.6;color:{V["ink"]};">{_e(t.pace_note)}</p>'
                 f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                 f'style="border-collapse:collapse;background:#fafbfc;border-radius:8px;">'
                 + trow("Risk to avoid", t.risk_to_avoid)
                 + trow("Acceleration move", t.acceleration_move)
                 + trow("Suggested next gate", t.suggested_next_gate)
                 + "</table>")
        rows.append(_row(_section_h("\u23F1", "Timeline Guidance", V["violetMid"]) + inner))

    # ── Assessment score breakdown ──
    header = (f'<tr style="text-align:left;">'
              f'<th style="padding:9px 12px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;'
              f'color:{V["violetMid"]};border-bottom:2px solid {V["violet"]};">Dimension</th>'
              f'<th style="padding:9px 12px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;'
              f'color:{V["violetMid"]};border-bottom:2px solid {V["violet"]};">Score</th>'
              f'<th style="padding:9px 12px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;'
              f'color:{V["violetMid"]};border-bottom:2px solid {V["violet"]};">Weight</th>'
              f'<th style="padding:9px 12px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;'
              f'color:{V["violetMid"]};border-bottom:2px solid {V["violet"]};">Assessment</th></tr>')
    body_rows = ""
    for d in a.dimensions:
        comment = (n.dimension_commentary.get(d.dimension, "") if n else "") or d.summary
        body_rows += (f'<tr>'
                      f'<td style="padding:10px 12px;font-size:13px;color:{V["ink"]};'
                      f'border-bottom:1px solid {V["line"]};"><b>{_e(d.dimension_label)}</b>'
                      f'<br><span style="font-size:11px;color:{V["muted"]};">({_e(d.agent)})</span></td>'
                      f'<td style="padding:10px 12px;font-size:13px;white-space:nowrap;'
                      f'border-bottom:1px solid {V["line"]};"><b>{d.value}/100</b></td>'
                      f'<td style="padding:10px 12px;font-size:13px;white-space:nowrap;'
                      f'border-bottom:1px solid {V["line"]};">{d.weight}%</td>'
                      f'<td style="padding:10px 12px;font-size:12.5px;line-height:1.55;color:{V["ink"]};'
                      f'border-bottom:1px solid {V["line"]};">{_e(comment)}</td></tr>')
    total_row = (f'<tr><td colspan="2" style="padding:11px 12px;background:{V["violetMid"]};color:#ffffff;'
                 f'font-size:13px;font-weight:700;">WEIGHTED TOTAL &nbsp; {score_text}</td>'
                 f'<td style="padding:11px 12px;background:{V["violetMid"]};color:#ffffff;font-size:13px;">100%</td>'
                 f'<td style="padding:11px 12px;background:{V["violetMid"]};color:#f3e8ff;font-size:13px;">'
                 f'{_e(a.rating)}</td></tr>')
    rows.append(_row(
        _section_h("\U0001F4CA", "Assessment Score Breakdown", V["violetMid"])
        + f'<p style="margin:0 0 8px;font-size:12px;color:{V["muted"]};">Weight set applied: '
          f'{_e(a.verdict.weight_set_version)} (stage-adaptive).</p>'
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
          f'style="border-collapse:collapse;">{header}{body_rows}{total_row}</table>'))

    # ── Recommended next steps ──
    if steps:
        rows.append(_row(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;"><tr><td bgcolor="{V["violetD"]}" '
            f'style="background:{V["violetD"]};border-radius:10px;padding:18px 22px;">'
            f'<div style="font-size:15px;font-weight:700;color:#ffffff;margin:0 0 10px;">'
            f'\U0001F4CC Recommended Next Steps</div>'
            f'<ol style="margin:0;padding-left:20px;font-size:13px;line-height:1.65;color:#ede9fe;">'
            + "".join(f'<li style="margin:7px 0;">{_e(s)}</li>' for s in steps)
            + '</ol></td></tr></table>'))

    # ── Resubmission invitation ──
    rows.append(_row(
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;"><tr><td style="border:2px dashed {V["greenBar"]};'
        f'border-radius:10px;padding:16px 20px;text-align:center;background:#fbfefc;">'
        f'<div style="font-size:14px;font-weight:700;color:{V["green"]};margin:0 0 5px;">'
        f'\U0001F331 We welcome resubmissions!</div>'
        f'<div style="font-size:12.5px;line-height:1.6;color:{V["ink"]};">Strengthen the submission using '
        f'the recommendations above and submit again \u2014 each iteration makes the next gate transition '
        f'faster and smoother.</div></td></tr></table>'))

    # ── Closing + footer ──
    closing = (n.closing_note if n and n.closing_note else "")
    hitl = ('<div style="font-size:11.5px;color:' + V["amber"] + ';margin:10px 0 0;">'
            '\u26A0 This is a recommendation \u2014 gate decisions are confirmed by a human reviewer.</div>'
            if (a.verdict.requires_human_review or a.verdict.gate_decision != GateDecision.GATE_PASS) else "")
    rows.append(_row(
        (f'<p style="margin:0 0 4px;font-size:13.5px;line-height:1.65;color:{V["ink"]};text-align:center;">'
         f'<b>{_e(closing)}</b></p>' if closing else "")
        + f'<p style="margin:10px 0 0;font-size:12px;color:{V["muted"]};text-align:center;">Questions or need '
          f'support? Contact the TI AI Team</p>'
        + f'<p style="margin:4px 0 0;font-size:11px;color:#8795a1;text-align:center;">Generated by the AI Pilot '
          f'Stage-Gate Evaluation System | Siemens Energy \u00b7 {_e(assessed)} \u00b7 {_e(gate_txt)}</p>'
        + hitl.replace('margin:10px 0 0;', 'margin:8px 0 0;text-align:center;')
        + f'<p style="margin:10px 0 0;font-size:10.5px;color:#8795a1;text-align:center;line-height:1.5;">'
          f'<b>How to read this assessment:</b> \u201cObserved\u201d = stated in your submission \u00b7 '
          f'\u201clikely / inferred\u201d = Oliver\u2019s reasoning from that evidence \u00b7 '
          f'\u201cassumed\u201d = a premise not stated in the submission \u00b7 '
          f'\u201cprojected\u201d = claimed but not yet measured.</p>'
        + f'<p style="margin:16px 0 0;font-size:13px;color:{V["ink"]};text-align:center;">Best regards,<br>'
          f'<b>Oliver Smith</b></p>'))

    body = "".join(rows)
    position = a.position or ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Oliver Assessment \u2014 {_e(sub.input.title)}</title></head>
<body style="margin:0;padding:0;background:#eef0f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="border-collapse:collapse;background:#eef0f2;"><tr><td align="center" style="padding:26px 12px;">
<table role="presentation" width="660" cellpadding="0" cellspacing="0" border="0"
  style="border-collapse:collapse;width:660px;max-width:660px;background:#ffffff;
  border:1px solid {V["line"]};border-radius:12px;overflow:hidden;
  font-family:'Segoe UI',Roboto,Arial,sans-serif;">

  <tr><td bgcolor="{V["violetMid"]}" style="background:{V["violetMid"]};
    background:linear-gradient(135deg,{V["violet"]},{V["violetD"]});padding:8px 28px 0;text-align:center;">
    <div style="font-size:26px;line-height:1;">\U0001F331</div></td></tr>
  <tr><td bgcolor="{V["violetMid"]}" style="background:{V["violetMid"]};
    background:linear-gradient(135deg,{V["violet"]},{V["violetD"]});padding:10px 28px 24px;text-align:center;">
    <div style="font-size:21px;font-weight:700;color:#ffffff;">Stage: {_e(stage_txt)}</div>
    <div style="font-size:14px;color:#f3e8ff;margin-top:6px;">Overall Score: {score_text}
      &nbsp;\u00b7&nbsp; Rating: {_e(a.rating)}</div>
    {f'<div style="font-size:12px;color:#dcc9f5;margin-top:10px;line-height:1.5;">Position: {_e(position)}</div>' if position else ''}
  </td></tr>

  {body}

  <tr><td style="padding:10px 28px 22px;"></td></tr>
</table>
</td></tr></table>
</body></html>"""
