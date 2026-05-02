import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { signInMock } = vi.hoisted(() => ({
  signInMock: vi.fn(),
}));

vi.mock("next-auth/react", () => ({
  signIn: signInMock,
}));

import type { ApiClient, StreamHandlers } from "@/lib/api";
import type {
  ChatStreamRequest,
  ConversationDetail,
  ConversationSummary,
  EmailMessage,
  EmailSummary,
  GmailStatus,
  MailTriageRequest,
  MailTriageResponse,
} from "@/lib/types";

import { MailDashboard } from "./MailDashboard";

afterEach(() => {
  vi.restoreAllMocks();
  signInMock.mockReset();
  window.localStorage.clear();
});

const inboxMessage: EmailSummary = {
  uid: "msg-1",
  from: "alice@example.com",
  to: ["reader@example.com"],
  subject: "Launch checklist",
  date: "2026-04-18T11:00:00Z",
  snippet: "Please review the launch checklist today.",
  unread: true,
  has_attachments: false,
};

const fullMessage: EmailMessage = {
  ...inboxMessage,
  body_text: "Please review the launch checklist today and send comments by 3 PM.",
  body_html: null,
  headers: {},
  message_id: "<msg-1@example.com>",
  in_reply_to: null,
  references: [],
  attachments: [],
  truncated: false,
};

class FakeMailApiClient implements ApiClient {
  public triagePayloads: MailTriageRequest[] = [];
  public streamPayloads: ChatStreamRequest[] = [];
  private conversation: ConversationDetail = {
    id: "mail-conversation-1",
    title: "Mail chat",
    created_at: "2026-04-18T10:00:00Z",
    updated_at: "2026-04-18T10:00:00Z",
    system_prompt_override: null,
    last_message_preview: null,
    messages: [],
  };

  constructor(
    private gmailStatus: GmailStatus,
    private readonly inbox: EmailSummary[] = [inboxMessage],
  ) {}

  async listConversations(): Promise<ConversationSummary[]> {
    return [this.conversation];
  }

  async createConversation(): Promise<ConversationSummary> {
    return this.conversation;
  }

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    if (conversationId !== this.conversation.id) throw new Error("Conversation not found.");
    return this.conversation;
  }

  async updateConversationSystemPrompt(): Promise<ConversationSummary> {
    throw new Error("Unexpected conversation update.");
  }

  async deleteConversation(): Promise<void> {
    throw new Error("Unexpected conversation deletion.");
  }

  async getGmailStatus(): Promise<GmailStatus> {
    return this.gmailStatus;
  }

  async disconnectGmail(): Promise<GmailStatus> {
    this.gmailStatus = { connected: false, email: null, scopes: [] };
    return this.gmailStatus;
  }

  getGmailLoginUrl(): string {
    return "/api/backend/auth/gmail/login";
  }

  async listMailInbox(): Promise<EmailSummary[]> {
    return this.inbox;
  }

  async getMailMessage(uid: string): Promise<EmailMessage> {
    return { ...fullMessage, uid };
  }

  async triageMail(payload: MailTriageRequest): Promise<MailTriageResponse> {
    this.triagePayloads.push(payload);
    return {
      triage_markdown:
        "**Sender**: alice@example.com\n**Subject**: Launch checklist\n**Date**: 2026-04-18T11:00:00Z\n**Unread**: yes\n**Summary** (1-2 sentences): Launch checklist needs review.\n**Priority**: high - same-day timing detected\n**Action items**:\n- Review the launch checklist\n**Deadlines**:\n- by 3 PM\n**Attachments**: none\n**Source**: configured inbox UID msg-1",
      steps: [
        {
          index: 0,
          kind: "tool",
          status: "ok",
          content: null,
          tool_name: "get_email",
          arguments: { uid: payload.uid ?? "msg-1" },
          result: { uid: payload.uid ?? "msg-1" },
          error: null,
        },
      ],
      source_uid: payload.uid ?? "msg-1",
      email: fullMessage,
    };
  }

  async streamConversationMessage(
    _conversationId: string,
    payload: ChatStreamRequest,
    handlers: StreamHandlers,
  ): Promise<void> {
    this.streamPayloads.push(payload);
    handlers.onEvent({
      type: "message_start",
      payload: {
        conversation: this.conversation,
        user_message: {
          id: "user-msg-1",
          role: "user",
          content: payload.message,
          created_at: "2026-04-18T11:01:00Z",
          sources: [],
        },
      },
    });
    handlers.onEvent({
      type: "agent_step",
      payload: {
        index: 0,
        kind: "tool",
        status: "ok",
        content: null,
        tool_name: payload.selected_email_uid ? "get_email" : "read_inbox",
        arguments: payload.selected_email_uid
          ? { uid: payload.selected_email_uid }
          : { limit: 10, unread_only: false },
        result: payload.selected_email_uid
          ? { uid: payload.selected_email_uid }
          : [{ uid: "msg-1" }],
        error: null,
      },
    });
    handlers.onEvent({ type: "assistant_delta", payload: { delta: "This mail needs review." } });
    handlers.onEvent({
      type: "message_complete",
      payload: {
        conversation: this.conversation,
        assistant_message: {
          id: "assistant-msg-1",
          role: "assistant",
          content: "This mail needs review.",
          created_at: "2026-04-18T11:01:01Z",
          sources: [],
        },
      },
    });
  }
}

test("mail dashboard shows Gmail sign-in when disconnected", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeMailApiClient({ connected: false, email: null, scopes: [] });

  render(<MailDashboard googleConfigured apiClient={apiClient} />);

  await waitFor(() =>
    expect(screen.getByRole("button", { name: /sign in with google/i })).toBeInTheDocument(),
  );
  expect(screen.getByText("Gmail not connected")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /sign in with google/i }));

  expect(signInMock).toHaveBeenCalledWith("google", { callbackUrl: "/mail" });
});

test("mail dashboard loads inbox and chat composer without the old body and triage panes", async () => {
  const apiClient = new FakeMailApiClient({
    connected: true,
    email: "reader@example.com",
    scopes: ["gmail.readonly"],
  });

  render(<MailDashboard googleConfigured apiClient={apiClient} />);

  await waitFor(() => expect(screen.getAllByText("Launch checklist").length).toBeGreaterThan(0));
  expect(screen.getByRole("textbox", { name: /message/i })).toBeInTheDocument();
  expect(screen.queryByText("Email body")).not.toBeInTheDocument();
  expect(screen.queryByText(/\*\*Priority\*\*: high/)).not.toBeInTheDocument();
  expect(screen.queryByText(/send comments by 3 PM/)).not.toBeInTheDocument();
});

test("mail dashboard streams mail chat with selected email uid", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeMailApiClient({
    connected: true,
    email: "reader@example.com",
    scopes: ["gmail.readonly"],
  });

  render(<MailDashboard googleConfigured apiClient={apiClient} />);

  await waitFor(() => expect(screen.getAllByText("Launch checklist").length).toBeGreaterThan(0));
  await user.type(screen.getByRole("textbox", { name: /message/i }), "summarize this mail");
  await user.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => expect(apiClient.streamPayloads).toHaveLength(1));
  expect(apiClient.streamPayloads[0]).toMatchObject({
    message: "summarize this mail",
    mode: "mail",
    selected_email_uid: "msg-1",
    max_steps: 5,
  });
  expect(apiClient.triagePayloads).toEqual([]);
  expect(await screen.findByText("This mail needs review.")).toBeInTheDocument();
});

test("mail dashboard streams inbox-wide mail chat without a selected email", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeMailApiClient(
    {
      connected: true,
      email: "reader@example.com",
      scopes: ["gmail.readonly"],
    },
    [],
  );

  render(<MailDashboard googleConfigured apiClient={apiClient} />);

  await waitFor(() => expect(screen.getByText("No matching Gmail messages were returned.")).toBeInTheDocument());
  await user.type(screen.getByRole("textbox", { name: /message/i }), "summarize this mail");
  await user.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => expect(apiClient.streamPayloads).toHaveLength(1));
  expect(apiClient.streamPayloads[0]).toMatchObject({
    message: "summarize this mail",
    mode: "mail",
    max_steps: 5,
  });
  expect(apiClient.streamPayloads[0].selected_email_uid).toBeUndefined();
});
