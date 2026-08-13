// Path: src/api.ts
// Description: Typed HTTP client for the admin backend.

import type { EmailThreadDetail, EmailThreadSummary } from "./lib/models";

const ADMIN_API_ROOT = (import.meta.env.VITE_ADMIN_API_URL || "/api").replace(/\/$/, "");
const API_V1 = `${ADMIN_API_ROOT}/v1`;

async function request<T>(path: string): Promise<T> {
    const response = await fetch(`${API_V1}${path}`, {
        credentials: "include",
    });
    if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail || `Request failed (${response.status})`);
    }
    return (await response.json()) as T;
}

export const api = {
    listEmailThreads: (): Promise<EmailThreadSummary[]> => request<EmailThreadSummary[]>("/email-threads"),
    getEmailThread: (id: string): Promise<EmailThreadDetail> => request<EmailThreadDetail>(`/email-threads/${id}`),
};
