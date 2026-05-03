import { parseEventStream } from "@/lib/sse";
import type {
  ChatStreamRequest,
  ConversationDetail,
  ConversationSummary,
  EmailMessage,
  EmailSummary,
  GmailStatus,
  MailTriageRequest,
  MailTriageResponse,
  StreamEvent,
} from "@/lib/types";

export interface StreamHandlers {
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

export interface ApiClient {
  listConversations(): Promise<ConversationSummary[]>;
  createConversation(): Promise<ConversationSummary>;
  getConversation(conversationId: string): Promise<ConversationDetail>;
  updateConversationSystemPrompt(
    conversationId: string,
    systemPromptOverride: string | null,
  ): Promise<ConversationSummary>;
  deleteConversation(conversationId: string): Promise<void>;
  getGmailStatus(): Promise<GmailStatus>;
  disconnectGmail(): Promise<GmailStatus>;
  getGmailLoginUrl(): string;
  listMailInbox(options?: { limit?: number; unread_only?: boolean }): Promise<EmailSummary[]>;
  getMailMessage(uid: string): Promise<EmailMessage>;
  triageMail(payload: MailTriageRequest): Promise<MailTriageResponse>;
  submitMailFeedback(conversationId: string, messageId: string, rating: 1 | -1): Promise<void>;
  streamConversationMessage(
    conversationId: string,
    payload: ChatStreamRequest,
    handlers: StreamHandlers,
  ): Promise<void>;
}

const DEFAULT_API_BASE_URL = "/api/backend";

export function resolveApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_PROXY_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  return DEFAULT_API_BASE_URL;
}

export function formatApiError(cause: unknown): string {
  if (!(cause instanceof Error)) {
    return `Unable to connect to the chat API at ${resolveApiBaseUrl()}.`;
  }

  if (cause.message === "Failed to fetch") {
    return `Unable to connect to the chat API through ${resolveApiBaseUrl()}. Make sure the Next.js proxy and FastAPI server are running.`;
  }

  return cause.message;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${resolveApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed.");
  }

  return (await response.json()) as T;
}

function toStreamEvent(eventName: string, payload: unknown): StreamEvent {
  switch (eventName) {
    case "message_start":
      return {
        type: "message_start",
        payload: payload as Extract<StreamEvent, { type: "message_start" }>["payload"],
      };
    case "step_update":
      return {
        type: "step_update",
        payload: payload as Extract<StreamEvent, { type: "step_update" }>["payload"],
      };
    case "assistant_delta":
      return {
        type: "assistant_delta",
        payload: payload as Extract<StreamEvent, { type: "assistant_delta" }>["payload"],
      };
    case "agent_step":
      return {
        type: "agent_step",
        payload: payload as Extract<StreamEvent, { type: "agent_step" }>["payload"],
      };
    case "source_add":
      return {
        type: "source_add",
        payload: payload as Extract<StreamEvent, { type: "source_add" }>["payload"],
      };
    case "message_complete":
      return {
        type: "message_complete",
        payload: payload as Extract<StreamEvent, { type: "message_complete" }>["payload"],
      };
    case "error":
      return {
        type: "error",
        payload: payload as Extract<StreamEvent, { type: "error" }>["payload"],
      };
    default:
      throw new Error(`Unknown stream event: ${eventName}`);
  }
}

export class HttpApiClient implements ApiClient {
  async listConversations(): Promise<ConversationSummary[]> {
    return requestJson<ConversationSummary[]>("/conversations");
  }

  async createConversation(): Promise<ConversationSummary> {
    return requestJson<ConversationSummary>("/conversations", {
      method: "POST",
      body: JSON.stringify({}),
    });
  }

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    return requestJson<ConversationDetail>(`/conversations/${conversationId}`);
  }

  async updateConversationSystemPrompt(
    conversationId: string,
    systemPromptOverride: string | null,
  ): Promise<ConversationSummary> {
    return requestJson<ConversationSummary>(`/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify({ system_prompt_override: systemPromptOverride }),
    });
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const response = await fetch(`${resolveApiBaseUrl()}/conversations/${conversationId}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "Unable to delete this conversation.");
    }
  }

  async getGmailStatus(): Promise<GmailStatus> {
    return requestJson<GmailStatus>("/auth/gmail/status");
  }

  async disconnectGmail(): Promise<GmailStatus> {
    return requestJson<GmailStatus>("/auth/gmail/logout", {
      method: "POST",
      body: JSON.stringify({}),
    });
  }

  getGmailLoginUrl(): string {
    return `${resolveApiBaseUrl()}/auth/gmail/login`;
  }

  async listMailInbox(options: { limit?: number; unread_only?: boolean } = {}): Promise<EmailSummary[]> {
    const params = new URLSearchParams();
    params.set("limit", String(options.limit ?? 20));
    params.set("unread_only", String(options.unread_only ?? true));
    const response = await requestJson<{ messages: EmailSummary[] }>(`/mail/inbox?${params}`);
    return response.messages;
  }

  async getMailMessage(uid: string): Promise<EmailMessage> {
    const response = await requestJson<{ message: EmailMessage }>(
      `/mail/messages/${encodeURIComponent(uid)}`,
    );
    return response.message;
  }

  async triageMail(payload: MailTriageRequest): Promise<MailTriageResponse> {
    return requestJson<MailTriageResponse>("/mail/triage", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async submitMailFeedback(conversationId: string, messageId: string, rating: 1 | -1): Promise<void> {
    const response = await fetch(
      `${resolveApiBaseUrl()}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/mail-feedback`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating }),
      },
    );
    if (!response.ok) {
      throw new Error(await response.text());
    }
  }

  async streamConversationMessage(
    conversationId: string,
    payload: ChatStreamRequest,
    handlers: StreamHandlers,
  ): Promise<void> {
    const response = await fetch(`${resolveApiBaseUrl()}/conversations/${conversationId}/messages/stream`, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json",
      },
      signal: handlers.signal,
    });

    if (!response.ok || !response.body) {
      const message = await response.text();
      throw new Error(message || "Unable to stream a response.");
    }

    await parseEventStream(response.body, (eventName, eventPayload) => {
      handlers.onEvent(toStreamEvent(eventName, eventPayload));
    });
  }
}

export function createBrowserApiClient(): ApiClient {
  return new HttpApiClient();
}
