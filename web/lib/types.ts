export type MessageRole = "user" | "assistant";
export type StepStatus = "pending" | "active" | "complete" | "error";
export type ChatStreamMode = "chat" | "agent" | "mail" | "news";

export interface SourceItem {
  title: string;
  source: string;
  published_at: string | null;
  url: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  sources: SourceItem[];
}

export interface UiMessage extends ChatMessage {
  pending?: boolean;
  error?: string | null;
  localOnly?: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  system_prompt_override?: string | null;
  last_message_preview: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

export interface StepUpdate {
  step_id: string;
  label: string;
  status: StepStatus;
}

export interface ChatStreamRequest {
  message: string;
  system_prompt?: string;
  mode?: ChatStreamMode;
  max_steps?: number;
  selected_email_uid?: string;
}

export interface GmailStatus {
  connected: boolean;
  email: string | null;
  scopes: string[];
}

export interface EmailAttachment {
  filename: string | null;
  content_type: string;
  size_bytes: number;
  content_id: string | null;
  disposition: string | null;
}

export interface EmailSummary {
  uid: string;
  from: string;
  to: string[];
  subject: string;
  date: string;
  snippet: string;
  unread: boolean;
  has_attachments: boolean;
}

export interface EmailMessage extends EmailSummary {
  body_text: string;
  body_html: string | null;
  headers: Record<string, string>;
  message_id: string;
  in_reply_to: string | null;
  references: string[];
  attachments: EmailAttachment[];
  truncated: boolean;
}

export interface MailTriageRequest {
  uid?: string;
  limit?: number;
  unread_only?: boolean;
}

export interface MailTriageResponse {
  triage_markdown: string;
  steps: AgentStep[];
  source_uid: string | null;
  email: EmailMessage | EmailSummary | null;
}

export interface AgentStep {
  index: number;
  kind: "model" | "tool";
  status: "ok" | "error";
  content: string | null;
  tool_name: string | null;
  arguments: Record<string, unknown> | null;
  result: unknown;
  error: string | null;
}

export interface HardwareInfo {
  device: "cuda" | "mps" | "cpu";
  gpu_name: string | null;
  vram_gb: number | null;
  compute_dtype: "float16" | "bfloat16" | "float32";
  quantization: "4bit" | "none";
  recommended_model: string;
  recommended_max_tokens: number;
  warning: string | null;
}

export type StreamEvent =
  | {
      type: "message_start";
      payload: {
        conversation: ConversationSummary;
        user_message: ChatMessage;
      };
    }
  | {
      type: "step_update";
      payload: StepUpdate;
    }
  | {
      type: "assistant_delta";
      payload: {
        delta: string;
      };
    }
  | {
      type: "agent_step";
      payload: AgentStep;
    }
  | {
      type: "source_add";
      payload: SourceItem;
    }
  | {
      type: "message_complete";
      payload: {
        conversation: ConversationSummary;
        assistant_message: ChatMessage;
      };
    }
  | {
      type: "error";
      payload: {
        message: string;
      };
    };
