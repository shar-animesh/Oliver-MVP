// Path: src/lib/models/email-thread.ts
// Description: TypeScript contracts for Oliver email communication history.

export interface EmailThreadSummary {
    id: string;
    conversation_id: string;
    subject: string | null;
    participant_email: string | null;
    message_count: number;
    last_activity_at: string;
}

export interface EmailMessage {
    id: string;
    direction: "INBOUND" | "OUTBOUND";
    sender_email: string | null;
    recipient_emails: string | null;
    subject: string | null;
    content_html: string | null;
    received_at: string;
}

export interface OliverRun {
    id: string;
    action: "SEND_EMAIL" | "NO_REPLY";
    model_name: string;
    subject: string | null;
    related_ideas: RelatedIdea[];
    prompt_tokens: number | null;
    completion_tokens: number | null;
    created_at: string;
}

export interface RelatedIdea {
    thread_id: string;
    subject: string | null;
    participant_email: string | null;
    rank: number;
    cosine_distance: number;
}

export interface EmailThreadDetail {
    id: string;
    conversation_id: string;
    subject: string | null;
    participant_email: string | null;
    embedding_model: string | null;
    embedding_dimensions: number | null;
    embedded_at: string | null;
    created_at: string;
    updated_at: string;
    messages: EmailMessage[];
    runs: OliverRun[];
}
