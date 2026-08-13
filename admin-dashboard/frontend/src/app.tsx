// Path: src/app.tsx
// Description: Top-level shell for the Oliver communications dashboard.

import EmailThreads from "./pages/email-threads";

export default function App() {
    return (
        <div className="app-shell">
            <header>
                <div className="header-left">
                    <h1>
                        <span>Oliver</span> Operations Console
                    </h1>
                    <p className="header-sub">Email communication and decision history</p>
                </div>
                <span className="tag">Read only</span>
            </header>
            <EmailThreads />
        </div>
    );
}
