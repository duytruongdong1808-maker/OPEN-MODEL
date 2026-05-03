"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { signIn, signOut } from "next-auth/react";

import {
  IconAlert,
  IconCpu,
  IconLogOut,
  IconMail,
  IconMenu,
  IconRetry,
  IconSend,
} from "@/components/ui/icons";
import type { ApiClient } from "@/lib/api";
import { createBrowserApiClient } from "@/lib/api";
import { formatPublishedAt, truncatePreview } from "@/lib/format";
import type {
  AgentStep,
  ChatStreamMode,
  EmailSummary,
  GmailStatus,
  StepUpdate,
  StreamEvent,
  UiMessage,
} from "@/lib/types";
import { Composer } from "@/features/chat/components/Composer";
import { MessageThread } from "@/features/chat/components/MessageThread";

interface MailDashboardProps {
  googleConfigured: boolean;
  apiClient?: ApiClient;
}

const MAIL_CONVERSATION_STORAGE_KEY = "open-model-mail-conversation-id";

function createOptimisticMessage(role: "user" | "assistant", content: string): UiMessage {
  return {
    id: `temp-mail-${role}-${crypto.randomUUID()}`,
    role,
    content,
    created_at: new Date().toISOString(),
    sources: [],
    pending: true,
    error: null,
    localOnly: true,
  };
}

function agentStepLabel(step: AgentStep): string {
  if (step.kind === "tool") return step.tool_name ? `Tool: ${step.tool_name}` : "Tool call";
  return "Model";
}

function agentStepToRuntimeStep(step: AgentStep, position: number): StepUpdate {
  return {
    step_id: `mail-${position}-${step.kind}-${step.tool_name ?? "model"}-${step.index}`,
    label: agentStepLabel(step),
    status: step.status === "error" ? "error" : "complete",
  };
}

export function MailDashboard({ googleConfigured, apiClient: injectedApiClient }: MailDashboardProps) {
  const [apiClient] = useState(() => injectedApiClient ?? createBrowserApiClient());
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [messages, setMessages] = useState<EmailSummary[]>([]);
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState("Mail chat");
  const [chatMessages, setChatMessages] = useState<UiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [liveSteps, setLiveSteps] = useState<StepUpdate[]>([]);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [messageModes, setMessageModes] = useState<Record<string, ChatStreamMode>>({});
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingInbox, setLoadingInbox] = useState(true);
  const [loadingChat, setLoadingChat] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [mobileInboxOpen, setMobileInboxOpen] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const draftRef = useRef(draft);
  const isStreamingRef = useRef(isStreaming);

  const connected = gmailStatus?.connected ?? false;
  const selectedSummary = useMemo(
    () => messages.find((message) => message.uid === selectedUid) ?? null,
    [messages, selectedUid],
  );

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    document.getElementById("mail-thread-anchor")?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatMessages, liveSteps]);

  const refreshGmailStatus = useCallback(async () => {
    try {
      setGmailStatus(await apiClient.getGmailStatus());
    } catch {
      setGmailStatus({ connected: false, email: null, scopes: [] });
    }
  }, [apiClient]);

  const ensureMailConversation = useCallback(async () => {
    setLoadingChat(true);
    try {
      const storedId =
        typeof window !== "undefined"
          ? window.localStorage.getItem(MAIL_CONVERSATION_STORAGE_KEY)
          : null;
      if (storedId) {
        try {
          const conversation = await apiClient.getConversation(storedId);
          setConversationId(conversation.id);
          setConversationTitle(conversation.title || "Mail chat");
          setChatMessages(conversation.messages);
          return conversation.id;
        } catch {
          window.localStorage.removeItem(MAIL_CONVERSATION_STORAGE_KEY);
        }
      }

      const conversation = await apiClient.createConversation();
      window.localStorage.setItem(MAIL_CONVERSATION_STORAGE_KEY, conversation.id);
      setConversationId(conversation.id);
      setConversationTitle(conversation.title || "Mail chat");
      setChatMessages([]);
      return conversation.id;
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Unable to prepare mail chat.");
      return null;
    } finally {
      setLoadingChat(false);
    }
  }, [apiClient]);

  const selectMessage = useCallback((uid: string) => {
    setSelectedUid(uid);
    setMobileInboxOpen(false);
    setNotice(null);
    setLiveSteps([]);
    setAgentSteps([]);
  }, []);

  const loadInbox = useCallback(
    async (nextUnreadOnly = unreadOnly) => {
      setLoadingInbox(true);
      setNotice(null);
      try {
        const inbox = await apiClient.listMailInbox({ limit: 20, unread_only: nextUnreadOnly });
        setMessages(inbox);
        setSelectedUid((current) => {
          if (current && inbox.some((message) => message.uid === current)) return current;
          return inbox[0]?.uid ?? null;
        });
      } catch (cause) {
        setNotice(cause instanceof Error ? cause.message : "Unable to load Gmail inbox.");
      } finally {
        setLoadingInbox(false);
      }
    },
    [apiClient, unreadOnly],
  );

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      await ensureMailConversation();
      if (cancelled) return;
      await refreshGmailStatus();
      if (cancelled) return;
      setLoadingInbox(false);
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [ensureMailConversation, refreshGmailStatus]);

  useEffect(() => {
    if (!connected) return;
    void loadInbox(unreadOnly);
  }, [connected, loadInbox, unreadOnly]);

  const handleGoogleLogin = useCallback(() => {
    if (!googleConfigured) {
      setNotice("Google sign-in is not configured on this server.");
      return;
    }
    void signIn("google", { callbackUrl: "/mail" });
  }, [googleConfigured]);

  const handleSignOut = useCallback(() => {
    void signOut({ callbackUrl: "/login" });
  }, []);

  const updateAssistantMessage = useCallback(
    (assistantId: string, nextValue: UiMessage | ((current: UiMessage) => UiMessage)) => {
      setChatMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message;
          return typeof nextValue === "function" ? nextValue(message) : nextValue;
        }),
      );
    },
    [],
  );

  const sendMessage = useCallback(
    async (promptOverride?: string) => {
      const prompt = (promptOverride ?? draftRef.current).trim();
      if (!prompt || isStreamingRef.current) return;
      if (!connected) {
        setNotice("Connect Gmail before asking about mail.");
        return;
      }

      const activeConversationId = conversationId ?? (await ensureMailConversation());
      if (!activeConversationId) return;

      const optimisticUser = createOptimisticMessage("user", prompt);
      const optimisticAssistant = createOptimisticMessage("assistant", "");
      const streamController = new AbortController();
      abortControllerRef.current = streamController;
      setDraft("");
      setLastPrompt(prompt);
      setNotice(null);
      setLiveSteps([]);
      setAgentSteps([]);
      setIsStreaming(true);
      setMessageModes((current) => ({ ...current, [optimisticAssistant.id]: "mail" }));
      setChatMessages((current) => [...current, optimisticUser, optimisticAssistant]);

      let streamErrored = false;
      const handleStreamEvent = (event: StreamEvent) => {
        switch (event.type) {
          case "message_start":
            setConversationTitle(event.payload.conversation.title || "Mail chat");
            setChatMessages((current) =>
              current.map((message) =>
                message.id === optimisticUser.id ? { ...event.payload.user_message } : message,
              ),
            );
            break;
          case "step_update":
            setLiveSteps((current) => {
              const remaining = current.filter((step) => step.step_id !== event.payload.step_id);
              return [...remaining, event.payload];
            });
            break;
          case "assistant_delta":
            updateAssistantMessage(optimisticAssistant.id, (current) => ({
              ...current,
              content: `${current.content}${event.payload.delta}`,
              pending: true,
              error: null,
            }));
            break;
          case "agent_step":
            setAgentSteps((current) => [...current, event.payload]);
            setLiveSteps((current) => [
              ...current,
              agentStepToRuntimeStep(event.payload, current.length),
            ]);
            break;
          case "source_add":
            break;
          case "message_complete":
            setConversationTitle(event.payload.conversation.title || "Mail chat");
            setMessageModes((current) => {
              const { [optimisticAssistant.id]: _removed, ...remaining } = current;
              return { ...remaining, [event.payload.assistant_message.id]: "mail" };
            });
            updateAssistantMessage(optimisticAssistant.id, {
              ...event.payload.assistant_message,
              pending: false,
            });
            break;
          case "error":
            streamErrored = true;
            setDraft(prompt);
            setNotice(event.payload.message);
            updateAssistantMessage(optimisticAssistant.id, (current) => ({
              ...current,
              pending: false,
              error: event.payload.message,
            }));
            setLiveSteps((current) =>
              current.map((step) => ({
                ...step,
                status: step.status === "complete" ? step.status : "error",
              })),
            );
            break;
        }
      };

      try {
        await apiClient.streamConversationMessage(
          activeConversationId,
          {
            message: prompt,
            mode: "mail",
            max_steps: 5,
            selected_email_uid: selectedUid || undefined,
          },
          { signal: streamController.signal, onEvent: handleStreamEvent },
        );
      } catch (cause) {
        if (streamController.signal.aborted) {
          setNotice("Generation stopped.");
          updateAssistantMessage(optimisticAssistant.id, (current) => ({ ...current, pending: false }));
        } else {
          const message = cause instanceof Error ? cause.message : "Unable to stream a response.";
          setDraft(prompt);
          setNotice(message);
          updateAssistantMessage(optimisticAssistant.id, (current) => ({
            ...current,
            pending: false,
            error: message,
          }));
        }
      } finally {
        abortControllerRef.current = null;
        setIsStreaming(false);
        if (!streamErrored) {
          setLiveSteps((current) =>
            current.map((step) => ({ ...step, status: step.status === "active" ? "complete" : step.status })),
          );
        }
      }
    },
    [apiClient, connected, conversationId, ensureMailConversation, selectedUid, updateAssistantMessage],
  );

  const handleSend = useCallback(() => {
    void sendMessage();
  }, [sendMessage]);

  const handleRetry = useCallback(() => {
    void sendMessage(lastPrompt ?? undefined);
  }, [lastPrompt, sendMessage]);

  const stopStreaming = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const handlePromptSelect = useCallback((prompt: string) => {
    setDraft(prompt);
  }, []);

  return (
    <main className="grid h-screen min-h-0 grid-cols-1 bg-bg-thread text-text lg:grid-cols-[340px_minmax(0,1fr)_360px]">
      <InboxRail
        connected={connected}
        email={gmailStatus?.email ?? null}
        googleConfigured={googleConfigured}
        loading={loadingInbox}
        messages={messages}
        mobileOpen={mobileInboxOpen}
        selectedUid={selectedUid}
        unreadOnly={unreadOnly}
        onCloseMobile={() => setMobileInboxOpen(false)}
        onGoogleLogin={handleGoogleLogin}
        onRefresh={() => void loadInbox(unreadOnly)}
        onSelect={selectMessage}
        onSignOut={handleSignOut}
        onUnreadOnlyChange={setUnreadOnly}
      />

      <section className="flex min-h-0 flex-col border-x border-line bg-bg-thread">
        <header className="flex items-center justify-between border-b border-line bg-bg-rail px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setMobileInboxOpen(true)}
            aria-label="Open inbox"
            className="om-icon-btn"
          >
            <IconMenu size={17} />
          </button>
          <div className="text-[13px] font-semibold">Mail Chat</div>
          <button
            type="button"
            aria-label="Refresh inbox"
            onClick={() => void loadInbox(unreadOnly)}
            className="om-icon-btn"
          >
            <IconRetry size={15} />
          </button>
        </header>

        {notice ? (
          <div className="mx-5 mt-4 flex items-start gap-2 rounded-md border border-warn-bd bg-warn-bg px-3 py-2.5 text-[12.5px] text-warn-fg">
            <IconAlert size={15} />
            <span>{notice}</span>
          </div>
        ) : null}

        <div className="om-scroll flex min-h-0 flex-1 flex-col overflow-y-auto">
          <MailContextBar summary={selectedSummary} />
          <MessageThread
            canRetry={Boolean(lastPrompt)}
            isLoading={loadingChat}
            liveSteps={liveSteps}
            messageModes={messageModes}
            messages={chatMessages}
            onPromptSelect={handlePromptSelect}
            onRetry={handleRetry}
            title={selectedSummary?.subject ? `Mail: ${selectedSummary.subject}` : conversationTitle}
          />
          <div id="mail-thread-anchor" />
        </div>

        <Composer
          draft={draft}
          disabled={!connected || loadingChat}
          isStreaming={isStreaming}
          canRetry={Boolean(lastPrompt)}
          onDraftChange={setDraft}
          onSend={handleSend}
          onStop={stopStreaming}
          onRetry={handleRetry}
        />
      </section>

      <AgentInspector
        connected={connected}
        email={gmailStatus?.email ?? null}
        running={isStreaming}
        sourceUid={selectedUid}
        selectedSummary={selectedSummary}
        steps={agentSteps}
      />
    </main>
  );
}

function MailContextBar({ summary }: { summary: EmailSummary | null }) {
  return (
    <div className="border-b border-line bg-bg-rail px-5 py-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-accent-ring bg-accent-soft text-accent-fg">
          <IconMail size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-text">
            {summary ? summary.subject || "(no subject)" : "Select an email to chat about"}
          </div>
          <div className="mt-0.5 truncate font-mono text-[10.5px] text-text-3">
            {summary
              ? `${summary.from} - UID ${summary.uid}`
              : "Mail chat will answer using the selected message only."}
          </div>
        </div>
      </div>
    </div>
  );
}

function InboxRail({
  connected,
  email,
  googleConfigured,
  loading,
  messages,
  mobileOpen,
  selectedUid,
  unreadOnly,
  onCloseMobile,
  onGoogleLogin,
  onRefresh,
  onSelect,
  onSignOut,
  onUnreadOnlyChange,
}: {
  connected: boolean;
  email: string | null;
  googleConfigured: boolean;
  loading: boolean;
  messages: EmailSummary[];
  mobileOpen: boolean;
  selectedUid: string | null;
  unreadOnly: boolean;
  onCloseMobile: () => void;
  onGoogleLogin: () => void;
  onRefresh: () => void;
  onSelect: (uid: string) => void;
  onSignOut: () => void;
  onUnreadOnlyChange: (value: boolean) => void;
}) {
  return (
    <>
      {mobileOpen ? (
        <div className="fixed inset-0 z-20 bg-black/60 backdrop-blur-[2px] lg:hidden" onClick={onCloseMobile} />
      ) : null}
      <aside
        className={`om-scroll fixed inset-y-0 left-0 z-30 flex w-[min(360px,92vw)] flex-col overflow-y-auto border-r border-line bg-bg-rail transition-transform lg:static lg:z-auto lg:w-auto lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <header className="border-b border-line px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="om-meta">Gmail</div>
              <h1 className="mt-1 text-lg font-semibold tracking-tight">Mail Chat</h1>
            </div>
            <div className="flex items-center gap-1.5">
              <button type="button" onClick={onRefresh} aria-label="Refresh inbox" className="om-icon-btn">
                <IconRetry size={15} />
              </button>
              <button type="button" onClick={onSignOut} aria-label="Sign out" className="om-icon-btn">
                <IconLogOut size={15} />
              </button>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <span className="grid h-7 w-7 place-items-center rounded-md border border-accent-ring bg-accent-soft text-accent-fg">
              <IconMail size={14} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-medium">
                {connected ? email ?? "Gmail connected" : "Gmail not connected"}
              </div>
              <div className="font-mono text-[10px] text-text-3">
                {connected ? "selected email context" : "connect to read inbox"}
              </div>
            </div>
          </div>
          {!connected ? (
            <button
              type="button"
              onClick={onGoogleLogin}
              disabled={!googleConfigured}
              className="om-btn mt-3 w-full justify-center"
            >
              Sign in with Google
            </button>
          ) : (
            <div className="mt-3 grid grid-cols-2 gap-1 rounded-lg border border-line bg-bg-input p-1">
              <button
                type="button"
                onClick={() => onUnreadOnlyChange(true)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${
                  unreadOnly ? "bg-bg-emph text-text" : "text-text-3 hover:text-text"
                }`}
              >
                Unread
              </button>
              <button
                type="button"
                onClick={() => onUnreadOnlyChange(false)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${
                  !unreadOnly ? "bg-bg-emph text-text" : "text-text-3 hover:text-text"
                }`}
              >
                All inbox
              </button>
            </div>
          )}
        </header>

        <div className="flex-1">
          {loading ? (
            <div className="px-4 py-5 text-[12.5px] text-text-3">Loading inbox...</div>
          ) : messages.length === 0 ? (
            <div className="px-4 py-5 text-[12.5px] leading-6 text-text-3">
              {connected ? "No matching Gmail messages were returned." : "Connect Gmail to load messages."}
            </div>
          ) : (
            <ol>
              {messages.map((message) => (
                <li key={message.uid}>
                  <button
                    type="button"
                    onClick={() => onSelect(message.uid)}
                    className={`block w-full border-b border-line px-4 py-3 text-left transition-colors hover:bg-bg-raised ${
                      selectedUid === message.uid ? "bg-bg-emph" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-[13px] font-medium text-text">{message.from}</div>
                        <div className="mt-0.5 truncate text-[12.5px] text-text-2">{message.subject || "(no subject)"}</div>
                      </div>
                      {message.unread ? <span className="mt-1 h-2 w-2 rounded-full bg-accent-fg" /> : null}
                    </div>
                    <div className="mt-2 line-clamp-2 text-[12px] leading-5 text-text-3">
                      {truncatePreview(message.snippet, 118)}
                    </div>
                    <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-text-4">
                      <span>{formatPublishedAt(message.date)}</span>
                      <span>{message.has_attachments ? "attachment" : `UID ${message.uid}`}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </>
  );
}

function AgentInspector({
  connected,
  email,
  running,
  sourceUid,
  selectedSummary,
  steps,
}: {
  connected: boolean;
  email: string | null;
  running: boolean;
  sourceUid: string | null;
  selectedSummary: EmailSummary | null;
  steps: AgentStep[];
}) {
  return (
    <aside className="hidden min-h-0 flex-col bg-bg-rail lg:flex">
      <header className="border-b border-line px-4 py-4">
        <div className="om-meta">Agent</div>
        <h2 className="mt-1 text-[14px] font-semibold">{running ? "Reading selected mail..." : "Read-only trace"}</h2>
        <div className="mt-2 text-[12px] text-text-3">
          {connected ? email ?? "Gmail connected" : "Gmail disconnected"}
        </div>
      </header>
      <div className="border-b border-line px-4 py-3">
        <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-text-2">
          <div className="rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <div className="text-[10px] uppercase tracking-wider text-text-4">Mode</div>
            <div className="mt-0.5 text-text">mail chat</div>
          </div>
          <div className="rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <div className="text-[10px] uppercase tracking-wider text-text-4">Source</div>
            <div className="mt-0.5 truncate text-text">{sourceUid ? `UID ${sourceUid}` : "none"}</div>
          </div>
        </div>
        {selectedSummary ? (
          <div className="mt-3 rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <div className="truncate text-[12px] font-medium text-text">{selectedSummary.subject || "(no subject)"}</div>
            <div className="mt-1 truncate text-[11px] text-text-3">{selectedSummary.from}</div>
          </div>
        ) : null}
      </div>
      <div className="om-scroll min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {steps.length === 0 ? (
          <div className="rounded-md border border-dashed border-line-strong p-4 text-center text-[12px] leading-6 text-text-3">
            Tool calls appear here after the model reads the selected email.
          </div>
        ) : (
          <ol className="relative ml-1.5 border-l border-line pl-4">
            {steps.map((step, index) => (
              <li key={`${step.tool_name}-${index}`} className="relative pb-4 last:pb-0">
                <span className="absolute -left-[22px] top-1.5 h-2 w-2 rounded-full bg-ok-fg" />
                <div className="text-[12.5px] font-medium text-text">Tool: {step.tool_name}</div>
                <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-text-4">
                  step {String(index + 1).padStart(2, "0")} - {step.status}
                </div>
                <pre className="mt-2 max-h-32 overflow-hidden rounded-md border border-line bg-bg-raised px-2 py-1.5 font-mono text-[10.5px] leading-5 text-text-3">
                  {JSON.stringify(step.arguments ?? {}, null, 2)}
                </pre>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
