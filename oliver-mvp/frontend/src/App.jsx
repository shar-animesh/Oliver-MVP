import { useState, useCallback, useEffect } from "react";
import TestAssessment from "./pages/TestAssessment.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Portfolio from "./pages/Portfolio.jsx";
import { api } from "./api.js";

const VIEWS = { PORTFOLIO: "portfolio", TEST: "test", DETAIL: "detail" };

export default function App() {
  const [view, setView] = useState(VIEWS.PORTFOLIO);
  const [activeSubmission, setActiveSubmission] = useState(null);
  const [submissions, setSubmissions] = useState([]);

  const refresh = useCallback(() => {
    api.listSubmissions().then(setSubmissions);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const openDetail = useCallback((sub) => {
    setActiveSubmission(sub);
    setView(VIEWS.DETAIL);
  }, []);

  const onTestComplete = useCallback((sub) => {
    refresh();
    openDetail(sub);
  }, [refresh, openDetail]);

  return (
    <div className="app-shell">
      <header>
        <div className="header-left">
          <h1>
            <span>Oliver</span> Operations Console
          </h1>
          <p className="header-sub">AI Pilot Lifecycle Management · Siemens Energy TI</p>
        </div>
        <span className="tag">Localhost MVP · Mock Agents</span>
      </header>

      <nav>
        <button
          className={view === VIEWS.PORTFOLIO ? "active" : ""}
          onClick={() => setView(VIEWS.PORTFOLIO)}
        >
          Portfolio
        </button>
        <button
          className={view === VIEWS.TEST ? "active" : ""}
          onClick={() => setView(VIEWS.TEST)}
        >
          Test Assessment
        </button>
        {activeSubmission?.assessment && (
          <button
            className={view === VIEWS.DETAIL ? "active" : ""}
            onClick={() => setView(VIEWS.DETAIL)}
          >
            Inspection
          </button>
        )}
      </nav>

      {view === VIEWS.PORTFOLIO && (
        <Portfolio submissions={submissions} onSelect={openDetail} onRefresh={refresh} />
      )}
      {view === VIEWS.TEST && (
        <TestAssessment onComplete={onTestComplete} />
      )}
      {view === VIEWS.DETAIL && activeSubmission && (
        <Dashboard submission={activeSubmission} onBack={() => setView(VIEWS.PORTFOLIO)} />
      )}
    </div>
  );
}
