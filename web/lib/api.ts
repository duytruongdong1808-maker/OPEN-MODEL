import { parseEventStream } from "@/lib/sse";
import type {
  ChatStreamRequest,
  ConversationDetail,
  ConversationSummary,
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
  streamConversationMessage(
    conversationId: string,
    payload: ChatStreamRequest,
    handlers: StreamHandlers,
  ): Promise<void>;
}

function resolveApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }
  return `${window.location.protocol}//${window.location.hostname}:8000`;
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
