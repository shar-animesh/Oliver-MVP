import { useState } from "react";

const STATE_COLORS = {
  Active: { bg: "var(--go-bg)", color: "var(--go)" },
  Assessed: { bg: "var(--se-teal-light)", color: "var(--se-teal-dark)" },
  Stalled: { bg: "var(--conditional-bg)", color: "var(--conditional)" },
  Submitted: { bg: "#f0f0f5", color: "var(--text-muted)" },
  Stellar: { bg: "#ede9fe", color: "#7c3aed" },
};

const GATE_DISPLAY = {
  GATE_PASS: { text: "Gate Pass", cls: "rec-go" },
  NO_GO_RECOMMENDED: { text: "No-Go", cls: "rec-conditional" },
  COACHING_REJECT: { text: "Reject", cls: "rec-nogo" },
};

function StatChip({ label, value, color }) {
  return (
    <div className="stat-chip">
      <div className="stat-value" style={{ color }}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function Portfolio({ submissions, onSelect, onRefresh }) {
  const [filter, setFilter] = useState("all");

  const assessed = submissions.filter((s) => s.assessment);
  const passCount = assessed.filter((s) => s.assessment.verdict.gate_decision === "GATE_PASS").length;
  const nogoCount = assessed.filter((s) => s.assessment.verdict.gate_decision === "NO_GO_RECOMMENDED").length;
  const rejectCount = assessed.filter((s) => s.assessment.verdict.gate_decision === "COACHING_REJECT").length;
  const withScore = assessed.filter((s) => s.assessment.verdict.composite != null);
  const avgScore = withScore.length
    ? Math.round(withScore.reduce((sum, s) => sum + s.assessment.verdict.composite, 0) / withScore.length)
    : "—";

  const filtered = filter === "all"
    ? submissions
    : submissions.filter((s) => s.state === filter);

  return (
    <>
      <div className="mock-banner">
        <span className="mock-dot" />
        Mock mode — all assessments use the deterministic evidence rubric.
        Swap the mock evaluators for Azure AI Foundry agents to go live.
      </div>

      <div className="stats-row">
        <StatChip label="Total pilots" value={submissions.length} color="var(--se-navy)" />
        <StatChip label="Avg. composite" value={avgScore} color="var(--se-teal)" />
        <StatChip label="Gate Pass" value={passCount} color="var(--go)" />
        <StatChip label="No-Go" value={nogoCount} color="var(--conditional)" />
        <StatChip label="Reject" value={rejectCount} color="var(--nogo)" />
      </div>

      <div className="card">
        <div className="card-header">
          <h2>All Pilots</h2>
          <div className="card-actions">
            <select
              className="filter-select"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">All states</option>
              <option value="Active">Active</option>
              <option value="Assessed">Assessed</option>
              <option value="Stalled">Stalled</option>
              <option value="Submitted">Submitted</option>
            </select>
            <button className="btn btn-secondary btn-sm" onClick={onRefresh}>Refresh</button>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="empty-state">
            <p>
              {submissions.length === 0
                ? "No pilots in the registry yet. Use Test Assessment to run a sandbox evaluation."
                : "No pilots match this filter."}
            </p>
          </div>
        ) : (
          <div className="pilot-table">
            <div className="pilot-header">
              <span className="col-title">Pilot</span>
              <span className="col-stage">Stage</span>
              <span className="col-score">Score</span>
              <span className="col-rec">Gate</span>
              <span className="col-state">State</span>
              <span className="col-date">Date</span>
            </div>
            {filtered.map((s) => {
              const a = s.assessment;
              const stateStyle = STATE_COLORS[s.state] || STATE_COLORS.Submitted;
              const gateInfo = a ? (GATE_DISPLAY[a.verdict.gate_decision] || GATE_DISPLAY.NO_GO_RECOMMENDED) : null;
              return (
                <div key={s.id} className="pilot-row" onClick={() => onSelect(s)}>
                  <span className="col-title">
                    <strong>{s.input.title}</strong>
                  </span>
                  <span className="col-stage mono">
                    {a ? a.stage.assigned_stage : "—"}
                  </span>
                  <span className="col-score mono">
                    {a ? (a.verdict.composite != null ? a.verdict.composite : "—") : "—"}
                  </span>
                  <span className="col-rec">
                    {gateInfo && (
                      <span className={`rec-badge ${gateInfo.cls}`}>
                        {gateInfo.text}
                      </span>
                    )}
                  </span>
                  <span className="col-state">
                    <span className="state-chip" style={{ background: stateStyle.bg, color: stateStyle.color }}>
                      {s.state}
                    </span>
                  </span>
                  <span className="col-date mono">
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
