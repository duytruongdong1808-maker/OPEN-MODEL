import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ConversationSummary } from "@/lib/types";

import { ConversationSidebar } from "./ConversationSidebar";

const conversations: ConversationSummary[] = [
  {
    id: "thread-1",
    title: "First thread",
    created_at: "2026-04-18T10:00:00Z",
    updated_at: "2026-04-18T10:05:00Z",
    last_message_preview: "Preview one",
  },
  {
    id: "thread-2",
    title: "Second thread",
    created_at: "2026-04-18T10:00:00Z",
    updated_at: "2026-04-18T10:10:00Z",
    last_message_preview: "Preview two",
  },
];

test("sidebar selects a conversation and triggers the callback", async () => {
  const user = userEvent.setup();
  const onSelectConversation = vi.fn();

  render(
    <ConversationSidebar
      activeConversationId="thread-1"
      conversations={conversations}
      isCreatingConversation={false}
      open
      onClose={vi.fn()}
      onDeleteConversation={vi.fn()}
      onNewConversation={vi.fn()}
      onSelectConversation={onSelectConversation}
    />,
  );

  await user.click(screen.getByRole("button", { name: /open second thread/i }));
  expect(onSelectConversation).toHaveBeenCalledWith("thread-2");
});
