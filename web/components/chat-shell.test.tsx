import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatShell } from "@/components/chat-shell";
import type { ApiClient, StreamHandlers } from "@/lib/api";
import type { ChatStreamRequest, ConversationDetail, ConversationSummary, StreamEvent } from "@/lib/types";

class FakeApiClient implements ApiClient {
  constructor(
    private readonly conversation: ConversationDetail,
    private readonly streamEvents: StreamEvent[],
  ) {}

  async listConversations(): Promise<ConversationSummary[]> {
    return [this.conversation];
  }

  async createConversation(): Promise<ConversationSummary> {
    return this.conversation;
  }

  async getConversation(_conversationId: string): Promise<ConversationDetail> {
    return this.conversation;
  }

  async streamConversationMessage(
    _conversationId: string,
    _payload: ChatStreamRequest,
    handlers: StreamHandlers,
  ): Promise<void> {
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

test("chat shell streams optimistic messages and updates the source panel", async () => {
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

  const textbox = screen.getByPlaceholderText(/ask a question/i);
  await user.type(textbox, "Summarize the latest");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(screen.getAllByText("Summarize the latest").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Here is a concise briefing.").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Reuters item").length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: /hide sources panel/i })).toBeInTheDocument();
});

test("chat shell toggles the sources panel", async () => {
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

  await user.click(screen.getByRole("button", { name: /show sources panel/i }));
  expect(screen.getAllByText(/live reasoning surface/i).length).toBeGreaterThan(0);
});
