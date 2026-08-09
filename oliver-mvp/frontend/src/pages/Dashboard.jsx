import { useState, useEffect } from "react";
import { api } from "../api.js";

const GATE_LABELS = {
  GATE_PASS: { text: "Gate Pass", cls: "rec-go" },
  NO_GO_RECOMMENDED: { text: "No-Go Recommended", cls: "rec-conditional" },
  COACHING_REJECT: { text: "Coaching Reject", cls: "rec-nogo" },
};

const STAGE_NAMES = {
  DI1: "Concept", DI2: "Feasibility", DI3: "Prototype", DI4: "Pilot", DI5: "Scale",
};
const stageLabel = (s) => (STAGE_NAMES[s] ? `${s} — ${STAGE_NAMES[s]}` : s);

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 6 }}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

/* ── 1) Summary report — primary experience, historical Oliver format ── */
function SummaryReport({ submission }) {
  const a = submission.assessment;
  const reject = a.verdict.gate_decision === "COACHING_REJECT";
  const scoreText = reject ? "—" : `${a.verdict.composite} / 100`;

  return (
    <div className="card os-summary">
      <div className="os-banner">
        <div className="os-banner-main">
          <div className="os-stage">Stage: {stageLabel(a.stage.assigned_stage)}</div>
          <div className="os-scoreline">
            Overall Score: {scoreText} · Rating: {a.rating}
          </div>
          {a.position && <div className="os-position">{a.position}</div>}
        </div>
        <a className="btn btn-sm os-download" href={api.reportUrl(submission.id)} download>
          <DownloadIcon /> Download structured report
        </a>
      </div>

      <div className="os-body">
        <h3 className="os-h os-h-exec">📋 Executive Summary</h3>
        <p className="os-p">{a.executive_summary}</p>

        {a.strengths?.length > 0 && (
          <>
            <h3 className="os-h os-h-str">✅ What's Working Well</h3>
            <div className="os-box os-box-green">
              <ul>{a.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          </>
        )}

        {a.coaching.actions?.length > 0 && (
          <>
            <h3 className="os-h os-h-coach">💡 Coaching Recommendations</h3>
            {a.coaching.message && <p className="os-sub">{a.coaching.message}</p>}
            <div className="os-box os-box-violet">
              <ol>{a.coaching.actions.map((c, i) => <li key={i}>{c}</li>)}</ol>
            </div>
          </>
        )}

        {a.next_actions?.length > 0 && (
          <>
            <h3 className="os-h os-h-next">🎯 Next Actions</h3>
            <div className="os-box os-box-amber">
              <ul>{a.next_actions.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Confidence bar (used by dimension cards) ── */
function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  let color = "var(--go)";
  if (pct < 60) color = "var(--nogo)";
  else if (pct < 80) color = "var(--conditional)";
  return (
    <div className="conf-bar-wrap">
      <div className="conf-bar" style={{ width: `${pct}%`, background: color }} />
      <span className="conf-label">{pct}%</span>
    </div>
  );
}

/* ── 2) Detailed dimension-by-dimension (retained from before) ── */
function DimensionCard({ dim }) {
  return (
    <div className="agent-card">
      <div className="dim-header">
        <div>
          <div className="agent-name">{dim.agent}</div>
          <div className="dim-name">{dim.dimension_label}</div>
        </div>
        <div className="dim-weight-badge">w{dim.weight}</div>
      </div>
      <div className="agent-score">
        {dim.value}<span> / 100</span>
      </div>

      <div className="conf-section">
        <span className="conf-title">Confidence</span>
        <ConfidenceBar value={dim.confidence} />
      </div>

      <p>{dim.summary}</p>

      {dim.evidence.length > 0 && (
        <div className="agent-evidence">
          {dim.evidence.map((e, i) => (
            <span key={i} className="evidence-tag">{e}</span>
          ))}
        </div>
      )}

      {dim.gaps.length > 0 && (
        <div className="agent-gaps">
          {dim.gaps.map((g, i) => (
            <span key={i} className="gap-tag">{g}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function LifecyclePanel({ submission }) {
  const [cadence, setCadence] = useState(null);
  const [events, setEvents] = useState([]);
  const [msg, setMsg] = useState("");
  const load = async () => {
    try {
      setCadence(await api.cadence(submission.id));
      const all = await api.audit();
      setEvents(all.filter((e) => e.subject === submission.id));
    } catch (e) { /* ignore */ }
  };
  useEffect(() => { load(); }, [submission.id]);
  const advance = async () => {
    const r = await api.advance(submission.id);
    setMsg(r.advanced ? `Advanced to ${r.current_stage}` : "Not eligible — gate not passed");
    load();
  };
  const deliver = async () => {
    const r = await api.deliver(submission.id);
    setMsg(`Report delivered (${r.channel})`);
    load();
  };
  return (
    <div className="card">
      <h2>Lifecycle &amp; Governance</h2>
      {cadence && (
        <div className="audit-grid">
          <div><b>Current stage:</b> {cadence.stage}</div>
          <div><b>Days in stage:</b> {cadence.days_in_stage} / {cadence.target_days} target</div>
          <div><b>Cadence:</b> {cadence.stalled ? "\u26a0 Stalled — overdue" : "On track"}</div>
        </div>
      )}
      <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn" onClick={advance}>Advance to next gate</button>
        <button className="btn" onClick={deliver}>Deliver report</button>
        {msg && <span style={{ alignSelf: "center", color: "var(--se-teal)" }}>{msg}</span>}
      </div>
      {events.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <b style={{ fontSize: ".85rem" }}>Audit trail (this pilot)</b>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: ".82rem", lineHeight: 1.6 }}>
            {events.map((e, i) => (
              <li key={i}>{e.event_type} · {e.actor} · {new Date(e.at).toLocaleString()}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function Dashboard({ submission, onBack }) {
  const a = submission.assessment;
  if (!a) return <div className="card empty-state"><p>No assessment data.</p></div>;

  const gate = GATE_LABELS[a.verdict.gate_decision] || GATE_LABELS.NO_GO_RECOMMENDED;
  const reject = a.verdict.gate_decision === "COACHING_REJECT";

  return (
    <>
      <button className="back-link" onClick={onBack}>← Back to portfolio</button>

      <div className="mock-banner">
        <span className="mock-dot" />
        Mock assessment — scores are computed by a deterministic evidence rubric,
        not a live LLM. Each score is traceable to detected evidence below.
      </div>

      <div className="detail-header" style={{ marginBottom: 12 }}>
        <h2>{submission.input.title}</h2>
        <p className="detail-problem">{submission.input.problem_statement}</p>
      </div>

      {/* 1 — Summary report (primary) */}
      <SummaryReport submission={submission} />

      {/* 2 — Detailed dimension scores (retained) */}
      <div className="card">
        <h2>Dimension Scores</h2>
        <p className="card-description">
          Five canonical dimensions, each owned by one agent. Weights are
          stage-adaptive (shown as w<em>N</em> badges — the percentage contribution
          to the composite score at the assessed stage).
        </p>
        <div className="agents-grid">
          {a.dimensions.map((dim) => (
            <DimensionCard key={dim.dimension} dim={dim} />
          ))}
        </div>
      </div>

      {/* Assessment record & audit */}
      <div className="card">
        <h2>Assessment record &amp; audit</h2>
        <div className="audit-grid">
          <div><b>Gate decision:</b> <span className={`rec-badge ${gate.cls}`}>{gate.text}</span></div>
          <div><b>Lifecycle:</b> {a.stage.lifecycle_state}</div>
          <div><b>Composite:</b> {reject ? "—" : `${a.verdict.composite}/100`}</div>
          <div>
            <b>Composite confidence:</b>{" "}
            {a.verdict.composite_confidence != null
              ? `${Math.round(a.verdict.composite_confidence * 100)}%`
              : "—"}
          </div>
          <div><b>Assigned stage:</b> {a.stage.assigned_stage}</div>
          <div><b>Lowest-confidence dimension:</b> {a.verdict.lowest_confidence_dimension || "—"}</div>
          <div><b>Assessed:</b> {new Date(a.assessed_at).toLocaleString()}</div>
          <div><b>Model:</b> {a.verdict.model_version} · {a.verdict.weight_set_version}</div>
        </div>

        <p className="stage-rationale" style={{ marginTop: 12 }}>{a.stage.rationale}</p>

        {a.verdict.requires_human_review && (
          <p className="hitl-flag">⚠ Requires human review before decision is final</p>
        )}
        {a.verdict.consistency_flags.length > 0 && (
          <p className="consistency-flag">⚠ {a.verdict.consistency_flags.join("; ")}</p>
        )}
      </div>

      {/* 3 — Lifecycle & Governance (cadence · advance · deliver · audit) */}
      <LifecyclePanel submission={submission} />
    </>
  );
}
