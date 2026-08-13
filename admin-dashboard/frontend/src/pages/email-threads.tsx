// Path: src/pages/email-threads.tsx
// Description: Read-only Oliver email communication browser.

import { useEffect, useState } from "react";

import { api } from "../api";
import type { EmailThreadDetail, EmailThreadSummary } from "../lib/models";

function formatDate(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

export default function EmailThreads() {
    const [threads, setThreads] = useState<EmailThreadSummary[]>([]);
    const [selectedThread, setSelectedThread] = useState<EmailThreadDetail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        void api
            .listEmailThreads()
            .then(setThreads)
            .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load email threads"))
            .finally(() => setLoading(false));
    }, []);

    async function openThread(threadId: string): Promise<void> {
        setError(null);
        try {
            setSelectedThread(await api.getEmailThread(threadId));
        } catch (reason: unknown) {
            setError(reason instanceof Error ? reason.message : "Could not load the email thread");
        }
    }

    if (selectedThread) {
        return (
            <section>
                <button className="back-link" onClick={() => setSelectedThread(null)}>
                    Back to email threads
                </button>
                <div className="card thread-detail">
                    <div className="card-header">
                        <div>
                            <h2>{selectedThread.subject || "Untitled conversation"}</h2>
                            <p className="thread-participant">{selectedThread.participant_email || "Unknown participant"}</p>
                        </div>
                        <span className="state-chip">{selectedThread.messages.length} messages</span>
                    </div>
                    <div className="message-list">
                        {selectedThread.messages.map((message) => (
                            <article className={`message-card message-${message.direction.toLowerCase()}`} key={message.id}>
                                <div className="message-meta">
                                    <strong>{message.direction === "INBOUND" ? message.sender_email || "Sender" : "Oliver"}</strong>
                                    <span>{formatDate(message.received_at)}</span>
                                </div>
                                <iframe
                                    className="message-frame"
                                    sandbox=""
                                    srcDoc={message.content_html || "<p>No content recorded.</p>"}
                                    title={`${message.direction.toLowerCase()} email from ${message.sender_email || "Oliver"}`}
                                />
                            </article>
                        ))}
                    </div>
                    {selectedThread.runs.some((run) => run.related_ideas.length > 0) && (
                        <div className="related-ideas">
                            <h3>Related ideas used by Oliver</h3>
                            {selectedThread.runs.map((run) =>
                                run.related_ideas.map((idea) => (
                                    <button
                                        className="thread-row"
                                        key={`${run.id}-${idea.thread_id}`}
                                        onClick={() => void openThread(idea.thread_id)}>
                                        <span>
                                            <strong>{idea.subject || "Untitled related idea"}</strong>
                                            <small>{idea.participant_email || "Unknown participant"}</small>
                                        </span>
                                        <span>Rank {idea.rank}</span>
                                        <span>{Math.round((1 - idea.cosine_distance) * 100)}% similarity</span>
                                    </button>
                                )),
                            )}
                        </div>
                    )}
                </div>
            </section>
        );
    }

    return (
        <section className="card">
            <div className="card-header">
                <div>
                    <h2>Email threads</h2>
                    <p className="card-description">All inbound and outbound communication handled by Oliver.</p>
                </div>
                <span className="state-chip">{threads.length} threads</span>
            </div>
            {error && <p className="error-message">{error}</p>}
            {loading ? (
                <div className="empty-state">
                    <p>Loading email threads...</p>
                </div>
            ) : threads.length === 0 ? (
                <div className="empty-state">
                    <p>Oliver has not handled any email conversations yet.</p>
                </div>
            ) : (
                <div className="thread-list">
                    {threads.map((thread) => (
                        <button className="thread-row" key={thread.id} onClick={() => void openThread(thread.id)}>
                            <span>
                                <strong>{thread.subject || "Untitled conversation"}</strong>
                                <small>{thread.participant_email || "Unknown participant"}</small>
                            </span>
                            <span>{thread.message_count} messages</span>
                            <time>{formatDate(thread.last_activity_at)}</time>
                        </button>
                    ))}
                </div>
            )}
        </section>
    );
}
