import { useState } from "react";
import { api } from "../api.js";

export default function TestAssessment({ onComplete }) {
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const payload = {
        title,
        problem_statement: problem,
        description,
      };
      const created = await api.createSubmission(payload);
      const assessed = await api.assess(created.id);
      onComplete(assessed);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h2>Test Assessment</h2>
      <p className="card-description">
        Run a sandbox assessment to test the evaluation pipeline. Enter a
        submission as it would arrive by email. The rubric evaluators score five
        dimensions and the canonical engine determines the composite, gate
        decision, and DI stage.
      </p>

      <form onSubmit={submit}>
        <div className="form-stack">
          <div>
            <label htmlFor="title">Project title</label>
            <input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Predictive Maintenance for Gas Turbines"
              required
            />
          </div>

          <div>
            <label htmlFor="problem">Problem statement</label>
            <textarea
              id="problem"
              rows={3}
              value={problem}
              onChange={(e) => setProblem(e.target.value)}
              placeholder="What operational pain point does this address?"
              required
            />
          </div>

          <div>
            <label htmlFor="desc">Additional context <span className="label-hint">(optional)</span></label>
            <textarea
              id="desc"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Any extra detail the submitter included — approach ideas, value estimates, data references, team info. The agents will extract what they need."
            />
          </div>
        </div>

        {error && (
          <p style={{ color: "var(--nogo)", marginTop: 12, fontSize: "0.88rem" }}>
            {error}
          </p>
        )}

        <div className="btn-row">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Running agents…" : "Run Assessment"}
          </button>
        </div>

        <p className="sandbox-note">
          Mock mode: scores come from a deterministic evidence rubric — each of
          the five dimensions runs structural checks against your submission and
          every point awarded is traceable to detected evidence. No LLM is called;
          no data leaves this machine.
        </p>
      </form>
    </div>
  );
}
