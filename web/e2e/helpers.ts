import { expect, type Locator, type Page, type Route } from "@playwright/test";

export const SIGN_IN_PATH = "/login";
export const STORAGE_STATE_PATH = ".auth/user.json";

export function e2eCredentials() {
  return {
    username: process.env.E2E_USERNAME || process.env.AUTH_USERNAME || "ci",
    password: process.env.E2E_PASSWORD || process.env.AUTH_PASSWORD || "ci-password",
  };
}

export async function login(page: Page) {
  const { username, password } = e2eCredentials();
  await page.goto(`${SIGN_IN_PATH}?callbackUrl=/`);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL(/\/chat\/[^/?#]+/, { timeout: 15_000 });
}

export async function openExistingConversation(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/chat\/[^/?#]+/, { timeout: 15_000 });
  await expect(page.getByTestId("chat-thread")).toBeVisible();
  return currentConversationId(page);
}

export function currentConversationId(page: Page): string {
  const match = new URL(page.url()).pathname.match(/^\/chat\/([^/]+)$/);
  if (!match) throw new Error(`Expected a chat URL, got ${page.url()}`);
  return match[1];
}

export function timestamp() {
  return new Date().toISOString();
}

export function titleFromPrompt(prompt: string) {
  const normalized = prompt.trim().replace(/\s+/g, " ");
  return normalized.length <= 56 ? normalized : `${normalized.slice(0, 55).trim()}...`;
}

export function sseEvent(event: string, payload: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

export function conversationSummary(id: string, title: string, preview: string | null = null) {
  const now = timestamp();
  return {
    id,
    title,
    created_at: now,
    updated_at: now,
    last_message_preview: preview,
  };
}

export function chatMessage(
  id: string,
  role: "user" | "assistant",
  content: string,
  sources = [],
) {
  return {
    id,
    role,
    content,
    created_at: timestamp(),
    sources,
  };
}

export async function fulfillChatStream(
  route: Route,
  options: {
    conversationId: string;
    prompt: string;
    assistantChunks: string[];
    title?: string;
  },
) {
  const title = options.title ?? titleFromPrompt(options.prompt);
  const assistantText = options.assistantChunks.join("");
  const started = conversationSummary(options.conversationId, title, options.prompt);
  const completed = conversationSummary(options.conversationId, title, assistantText);
  const body = [
    sseEvent("message_start", {
      conversation: started,
      user_message: chatMessage(`user-${Date.now()}`, "user", options.prompt),
    }),
    sseEvent("step_update", {
      step_id: "context",
      label: "Reading conversation",
      status: "active",
    }),
    sseEvent("step_update", {
      step_id: "context",
      label: "Reading conversation",
      status: "complete",
    }),
    sseEvent("step_update", {
      step_id: "draft",
      label: "Drafting answer",
      status: "active",
    }),
    ...options.assistantChunks.map((delta) => sseEvent("assistant_delta", { delta })),
    sseEvent("step_update", {
      step_id: "draft",
      label: "Drafting answer",
      status: "complete",
    }),
    sseEvent("message_complete", {
      conversation: completed,
      assistant_message: chatMessage(`assistant-${Date.now()}`, "assistant", assistantText),
    }),
  ].join("");

  await route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    body,
  });
}

export async function fulfillAgentStream(
  route: Route,
  options: {
    conversationId: string;
    prompt: string;
    answer: string;
    title?: string;
  },
) {
  const title = options.title ?? titleFromPrompt(options.prompt);
  const started = conversationSummary(options.conversationId, title, options.prompt);
  const completed = conversationSummary(options.conversationId, title, options.answer);
  const body = [
    sseEvent("message_start", {
      conversation: started,
      user_message: chatMessage(`user-${Date.now()}`, "user", options.prompt),
    }),
    sseEvent("agent_step", {
      index: 1,
      kind: "model",
      status: "ok",
      content: "Need to inspect unread inbox.",
      tool_name: null,
      arguments: null,
      result: null,
      error: null,
    }),
    sseEvent("agent_step", {
      index: 2,
      kind: "tool",
      status: "ok",
      content: null,
      tool_name: "read_inbox",
      arguments: { unread_only: true, limit: 5 },
      result: { count: 1 },
      error: null,
    }),
    sseEvent("message_complete", {
      conversation: completed,
      assistant_message: chatMessage(`assistant-${Date.now()}`, "assistant", options.answer),
    }),
  ].join("");

  await route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    body,
  });
}

export function activeConversationItem(page: Page): Locator {
  return page.locator('[data-testid="conversation-item"][data-active="true"]');
}
