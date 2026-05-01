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

  constructor(
    private gmailStatus: GmailStatus,
    private readonly inbox: EmailSummary[] = [inboxMessage],
  ) {}

  async listConversations(): Promise<ConversationSummary[]> {
    return [];
  }

  async createConversation(): Promise<ConversationSummary> {
    throw new Error("Unexpected conversation creation.");
  }

  async getConversation(_conversationId: string): Promise<ConversationDetail> {
    throw new Error("Unexpected conversation lookup.");
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
    _handlers: StreamHandlers,
  ): Promise<void> {
    this.streamPayloads.push(payload);
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

test("mail dashboard loads inbox, selected email, and triage", async () => {
  const apiClient = new FakeMailApiClient({
    connected: true,
    email: "reader@example.com",
    scopes: ["gmail.readonly"],
  });

  render(<MailDashboard googleConfigured apiClient={apiClient} />);

  await waitFor(() => expect(screen.getAllByText("Launch checklist").length).toBeGreaterThan(0));
  expect(screen.getByText(/Please review the launch checklist today and send comments/)).toBeInTheDocument();
  expect(screen.getByText(/\*\*Priority\*\*: high/)).toBeInTheDocument();
  expect(screen.getAllByText("Tool: get_email").length).toBeGreaterThan(0);
  expect(apiClient.triagePayloads[0]).toEqual({ uid: "msg-1" });
});

test("mail dashboard composer uses mail triage instead of chat streaming", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeMailApiClient({
    connected: true,
    email: "reader@example.com",
    scopes: ["gmail.readonly"],
  });

  render(<MailDashboard googleConfigured apiClient={apiClient} />);

  await waitFor(() => expect(screen.getAllByText("Launch checklist").length).toBeGreaterThan(0));
  await user.type(screen.getByRole("textbox", { name: /ask mail agent/i }), "What should I do?");
  await user.click(screen.getByRole("button", { name: /ask/i }));

  expect(apiClient.triagePayloads.at(-1)).toEqual({ uid: "msg-1" });
  expect(apiClient.streamPayloads).toEqual([]);
});
