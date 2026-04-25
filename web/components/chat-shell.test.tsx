import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatShell } from "@/components/chat-shell";
import type { ApiClient, StreamHandlers } from "@/lib/api";
import type { ChatStreamRequest, ConversationDetail, ConversationSummary, StreamEvent } from "@/lib/types";

afterEach(() => {
  vi.restoreAllMocks();
});

class FakeApiClient implements ApiClient {
  public streamPayloads: ChatStreamRequest[] = [];
  public createConversationCalls = 0;
  public deletedConversationIds: string[] = [];

  constructor(
    private readonly conversation: ConversationDetail,
    private readonly streamEvents: StreamEvent[],
    private conversations: ConversationSummary[] = [conversation],
    private readonly createdConversation: ConversationSummary = {
      id: "created-thread",
      title: "New chat",
      created_at: "2026-04-18T11:20:00Z",
      updated_at: "2026-04-18T11:20:00Z",
      last_message_preview: null,
    },
    private readonly createDelayMs = 0,
  ) {}

  async listConversations(): Promise<ConversationSummary[]> {
    return this.conversations;
  }

  async createConversation(): Promise<ConversationSummary> {
    this.createConversationCalls += 1;
    if (this.createDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.createDelayMs));
    }
    this.conversations = [this.createdConversation, ...this.conversations];
    return this.createdConversation;
  }

  async getConversation(_conversationId: string): Promise<ConversationDetail> {
    return this.conversation;
  }

  async deleteConversation(conversationId: string): Promise<void> {
    this.deletedConversationIds.push(conversationId);
    this.conversations = this.conversations.filter((item) => item.id !== conversationId);
  }

  async streamConversationMessage(
    _conversationId: string,
    payload: ChatStreamRequest,
    handlers: StreamHandlers,
  ): Promise<void> {
    this.streamPayloads.push(payload);
    for (const event of this.streamEvents) {
      handlers.onEvent(event);
    }
  }
}

const baseConversation: ConversationDetail = {
  id: "conversation-1",
  title: "Daily workspace",
  created_at: "2026-04-18T11:00:00Z",
  updated_at: "2026-04-18T11:00:00Z",
  last_message_preview: null,
  messages: [],
};

test("chat shell streams regular chat by default", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeApiClient(baseConversation, [
    {
      type: "message_start",
      payload: {
        conversation: {
          ...baseConversation,
          title: "Summarize the latest",
          last_message_preview: "Summarize the latest",
          updated_at: "2026-04-18T11:05:00Z",
        },
        user_message: {
          id: "user-1",
          role: "user",
          content: "Summarize the latest",
          created_at: "2026-04-18T11:05:00Z",
          sources: [],
        },
      },
    },
    {
      type: "step_update",
      payload: {
        step_id: "context",
        label: "Reading conversation",
        status: "active",
      },
    },
    {
      type: "assistant_delta",
      payload: {
        delta: "Here is",
      },
    },
    {
      type: "source_add",
      payload: {
        title: "Reuters item",
        source: "Reuters",
        published_at: "2026-04-18T10:59:00Z",
        url: "https://example.com/reuters",
      },
    },
    {
      type: "assistant_delta",
      payload: {
        delta: " a concise briefing.",
      },
    },
    {
      type: "message_complete",
      payload: {
        conversation: {
          ...baseConversation,
          title: "Summarize the latest",
          last_message_preview: "Here is a concise briefing.",
          updated_at: "2026-04-18T11:05:10Z",
        },
        assistant_message: {
          id: "assistant-1",
          role: "assistant",
          content: "Here is a concise briefing.",
          created_at: "2026-04-18T11:05:10Z",
          sources: [],
        },
      },
    },
  ]);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={vi.fn()}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  const textbox = screen.getByRole("textbox", { name: /message/i });
  await user.type(textbox, "Summarize the latest");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(screen.getAllByText("Summarize the latest").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Here is a concise briefing.").length).toBeGreaterThan(0);
  expect(apiClient.streamPayloads[0]).toMatchObject({ mode: "chat" });
  expect(apiClient.streamPayloads[0].max_steps).toBeUndefined();
  expect(screen.queryByText("Tool: read_inbox")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /sources/i }));
  expect(screen.getAllByText("Reuters item").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("button", { name: /hide runtime panel/i }).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /attach/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /search the web/i })).not.toBeInTheDocument();
});

test("chat shell switches to the read-only mail agent for inbox prompts", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeApiClient(baseConversation, [
    {
      type: "message_start",
      payload: {
        conversation: {
          ...baseConversation,
          title: "Tom tat mail chua doc",
          last_message_preview: "Tom tat mail chua doc",
          updated_at: "2026-04-18T11:05:00Z",
        },
        user_message: {
          id: "user-1",
          role: "user",
          content: "Tom tat mail chua doc",
          created_at: "2026-04-18T11:05:00Z",
          sources: [],
        },
      },
    },
    {
      type: "agent_step",
      payload: {
        index: 0,
        kind: "tool",
        status: "ok",
        content: null,
        tool_name: "read_inbox",
        arguments: { limit: 10, unread_only: true },
        result: [{ uid: "101", subject: "Launch checklist" }],
        error: null,
      },
    },
    {
      type: "message_complete",
      payload: {
        conversation: {
          ...baseConversation,
          title: "Tom tat mail chua doc",
          last_message_preview: "Inbox is quiet.",
          updated_at: "2026-04-18T11:05:10Z",
        },
        assistant_message: {
          id: "assistant-1",
          role: "assistant",
          content: "Inbox is quiet.",
          created_at: "2026-04-18T11:05:10Z",
          sources: [],
        },
      },
    },
  ]);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={vi.fn()}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.type(screen.getByRole("textbox", { name: /message/i }), "Tom tat mail chua doc");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(apiClient.streamPayloads[0]).toMatchObject({ mode: "agent", max_steps: 5 });
  expect(screen.getAllByText("Tool: read_inbox").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Mail agent").length).toBeGreaterThan(0);
});

test("chat shell keeps email drafting prompts in regular chat mode", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeApiClient(baseConversation, [
    {
      type: "message_complete",
      payload: {
        conversation: {
          ...baseConversation,
          title: "Soan email cam on",
          last_message_preview: "Here is a draft.",
          updated_at: "2026-04-18T11:05:10Z",
        },
        assistant_message: {
          id: "assistant-1",
          role: "assistant",
          content: "Here is a draft.",
          created_at: "2026-04-18T11:05:10Z",
          sources: [],
        },
      },
    },
  ]);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={vi.fn()}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.type(screen.getByRole("textbox", { name: /message/i }), "Soan giup toi mot email cam on");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(apiClient.streamPayloads[0]).toMatchObject({ mode: "chat" });
  expect(apiClient.streamPayloads[0].max_steps).toBeUndefined();
  expect(screen.queryByText("Mail agent")).not.toBeInTheDocument();
});

test("chat shell copies the latest agent response", async () => {
  const user = userEvent.setup();
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  const apiClient = new FakeApiClient(baseConversation, [
    {
      type: "message_complete",
      payload: {
        conversation: {
          ...baseConversation,
          title: "Tom tat mail",
          last_message_preview: "Inbox is quiet.",
          updated_at: "2026-04-18T11:05:10Z",
        },
        assistant_message: {
          id: "assistant-1",
          role: "assistant",
          content: "Inbox is quiet.",
          created_at: "2026-04-18T11:05:10Z",
          sources: [],
        },
      },
    },
  ]);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={vi.fn()}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.type(screen.getByRole("textbox", { name: /message/i }), "Tom tat mail");
  await user.click(screen.getByRole("button", { name: /send/i }));
  await user.click(screen.getByRole("button", { name: /copy/i }));

  expect(writeText).toHaveBeenCalledWith("Inbox is quiet.");
});

test("chat shell toggles the runtime panel", async () => {
  const user = userEvent.setup();
  const apiClient = new FakeApiClient(baseConversation, []);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={vi.fn()}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.click(screen.getAllByRole("button", { name: /hide runtime panel/i })[0]);
  await user.click(screen.getByRole("button", { name: /show runtime panel/i }));
  expect(screen.getByRole("complementary", { name: /runtime panel/i })).toBeInTheDocument();
});

test("new chat does not create another empty active thread", async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();
  const blankActiveConversation: ConversationDetail = {
    ...baseConversation,
    title: "New chat",
  };
  const apiClient = new FakeApiClient(blankActiveConversation, []);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={navigate}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /new chat/i })).toBeInTheDocument(),
  );

  await user.click(screen.getByRole("button", { name: /create new chat/i }));

  expect(apiClient.createConversationCalls).toBe(0);
  expect(navigate).not.toHaveBeenCalled();
});

test("new chat reuses an existing empty thread instead of creating one", async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();
  const activeConversation: ConversationDetail = {
    ...baseConversation,
    id: "active-thread",
    title: "Active thread",
    last_message_preview: "Hello",
    messages: [
      {
        id: "message-1",
        role: "user",
        content: "Hello",
        created_at: "2026-04-18T11:00:00Z",
        sources: [],
      },
    ],
  };
  const blankConversation: ConversationSummary = {
    id: "blank-thread",
    title: "New chat",
    created_at: "2026-04-18T11:10:00Z",
    updated_at: "2026-04-18T11:10:00Z",
    last_message_preview: null,
  };
  const apiClient = new FakeApiClient(activeConversation, [], [
    activeConversation,
    blankConversation,
  ]);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="active-thread"
      onNavigateConversation={navigate}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /active thread/i })).toBeInTheDocument(),
  );

  await user.click(screen.getByRole("button", { name: /create new chat/i }));

  expect(apiClient.createConversationCalls).toBe(0);
  expect(navigate).toHaveBeenCalledWith("blank-thread");
});

test("new chat double click creates only one empty thread", async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();
  const activeConversation: ConversationDetail = {
    ...baseConversation,
    id: "active-thread",
    title: "Active thread",
    last_message_preview: "Hello",
    messages: [
      {
        id: "message-1",
        role: "user",
        content: "Hello",
        created_at: "2026-04-18T11:00:00Z",
        sources: [],
      },
    ],
  };
  const apiClient = new FakeApiClient(activeConversation, [], [activeConversation], undefined, 20);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="active-thread"
      onNavigateConversation={navigate}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /active thread/i })).toBeInTheDocument(),
  );

  await user.dblClick(screen.getByRole("button", { name: /create new chat/i }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith("created-thread"));

  expect(apiClient.createConversationCalls).toBe(1);
});

test("delete conversation cancel does not call the API", async () => {
  const user = userEvent.setup();
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const apiClient = new FakeApiClient(baseConversation, []);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={vi.fn()}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.click(screen.getByRole("button", { name: /delete daily workspace/i }));

  expect(apiClient.deletedConversationIds).toEqual([]);
});

test("delete active conversation navigates to the nearest remaining thread", async () => {
  const user = userEvent.setup();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const navigate = vi.fn();
  const nextConversation: ConversationSummary = {
    id: "next-thread",
    title: "Next thread",
    created_at: "2026-04-18T11:10:00Z",
    updated_at: "2026-04-18T11:10:00Z",
    last_message_preview: "Next",
  };
  const apiClient = new FakeApiClient(baseConversation, [], [baseConversation, nextConversation]);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={navigate}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.click(screen.getByRole("button", { name: /delete daily workspace/i }));

  expect(apiClient.deletedConversationIds).toEqual(["conversation-1"]);
  expect(navigate).toHaveBeenCalledWith("next-thread");
});

test("delete the last conversation creates one replacement empty thread", async () => {
  const user = userEvent.setup();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const navigate = vi.fn();
  const apiClient = new FakeApiClient(baseConversation, []);

  render(
    <ChatShell
      apiClient={apiClient}
      conversationId="conversation-1"
      onNavigateConversation={navigate}
    />,
  );

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /daily workspace/i })).toBeInTheDocument(),
  );

  await user.click(screen.getByRole("button", { name: /delete daily workspace/i }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith("created-thread"));

  expect(apiClient.deletedConversationIds).toEqual(["conversation-1"]);
  expect(apiClient.createConversationCalls).toBe(1);
});
