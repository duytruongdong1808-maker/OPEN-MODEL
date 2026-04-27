import { expect, test } from "@playwright/test";

import {
  activeConversationItem,
  currentConversationId,
  fulfillChatStream,
  openExistingConversation,
  titleFromPrompt,
} from "./helpers";

test("user can send a message, see the sidebar entry, reload, and delete the conversation", async ({
  page,
}) => {
  await openExistingConversation(page);

  const prompt = `E2E chat flow ${Date.now()} creates a deterministic sidebar title`;
  const assistantText = "Hello from the mocked SSE stream.";
  let requestBody: unknown = null;

  await page.route("**/api/backend/conversations/*/messages/stream", async (route) => {
    requestBody = route.request().postDataJSON();
    await fulfillChatStream(route, {
      conversationId: currentConversationId(page),
      prompt,
      assistantChunks: ["Hello from ", "the mocked SSE stream."],
    });
  });

  await page.getByTestId("composer-input").fill(prompt);
  await page.getByTestId("composer-submit").click();

  await expect.poll(() => requestBody).toEqual({ message: prompt, mode: "chat" });
  await expect(page.locator('[data-testid="message"][data-role="assistant"]').last()).toContainText(
    assistantText,
  );
  await expect(page.getByTestId("conversation-item").filter({ hasText: titleFromPrompt(prompt) })).toBeVisible();

  const conversationUrl = page.url();
  const conversationId = currentConversationId(page);
  await page.reload();
  await expect(page).toHaveURL(conversationUrl);
  await expect(page.getByTestId("chat-thread")).toBeVisible();
  await expect(activeConversationItem(page)).toHaveAttribute("data-conversation-id", conversationId);

  page.once("dialog", (dialog) => dialog.accept());
  await activeConversationItem(page).getByRole("button", { name: /^delete /i }).click();
  await expect(
    page.locator(`[data-testid="conversation-item"][data-conversation-id="${conversationId}"]`),
  ).toHaveCount(0);
});
