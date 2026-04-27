import { expect, test } from "@playwright/test";

import { currentConversationId, fulfillAgentStream, openExistingConversation } from "./helpers";

test("agent mode renders agent steps and final assistant message", async ({ page }) => {
  await openExistingConversation(page);

  const prompt = `Read my unread inbox for E2E ${Date.now()}`;
  const answer = "You have one unread message that needs a reply.";
  let requestBody: unknown = null;

  await page.route("**/api/backend/conversations/*/messages/stream", async (route) => {
    requestBody = route.request().postDataJSON();
    await fulfillAgentStream(route, {
      conversationId: currentConversationId(page),
      prompt,
      answer,
    });
  });

  await page.getByTestId("composer-input").fill(prompt);
  await page.getByTestId("composer-submit").click();

  await expect.poll(() => requestBody).toEqual({ message: prompt, mode: "agent", max_steps: 5 });
  await expect(page.getByTestId("agent-status")).toContainText("Agent reasoning");
  await expect(page.getByTestId("agent-status")).toContainText("Tool: read_inbox");
  await expect(page.locator('[data-testid="message"][data-role="assistant"]').last()).toContainText(answer);
});
