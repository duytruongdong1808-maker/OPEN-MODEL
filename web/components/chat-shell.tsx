"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { signIn } from "next-auth/react";

import { AgentStatusPanel } from "@/components/agent-status-panel";
import { Composer } from "@/components/composer";
import { ConversationSidebar } from "@/components/conversation-sidebar";
import { IconAlert, IconMenu, IconModel, IconPanel } from "@/components/icons";
import { MessageThread } from "@/components/message-thread";
import type { ApiClient } from "@/lib/api";
import type {
  ConversationSummary,
  AgentStep,
  ChatStreamMode,
  GmailStatus,
  SourceItem,
  StreamEvent,
  StepUpdate,
  UiMessage,
} from "@/lib/types";

const DEFAULT_CONVERSATION_TITLE = "New chat";

function isBlankConversation(conversation: ConversationSummary | null | undefined): boolean {
  return (
    conversation?.title === DEFAULT_CONVERSATION_TITLE &&
    conversation.last_message_preview === null
  );
}

function sortConversationList(items: ConversationSummary[]): ConversationSummary[] {
  return [...items].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
}

function upsertConversation(
  items: ConversationSummary[],
  next: ConversationSummary,
): ConversationSummary[] {
  const remaining = items.filter((item) => item.id !== next.id);
  return sortConversationList([next, ...remaining]);
}

function createOptimisticMessage(role: "user" | "assistant", content: string): UiMessage {
  return {
    id: `temp-${role}-${crypto.randomUUID()}`,
    role,
    content,
    created_at: new Date().toISOString(),
    sources: [],
    pending: true,
    localOnly: true,
    error: null,
  };
}

function latestAssistantSources(messages: UiMessage[]): SourceItem[] {
  const latestAssistant = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && message.sources.length > 0);
  return latestAssistant?.sources ?? [];
}

function agentStepLabel(step: AgentStep): string {
  if (step.kind === "tool") {
    return step.tool_name ? `Tool: ${step.tool_name}` : "Tool call";
  }
  return step.status === "error" ? "Agent reasoning failed" : "Agent reasoning";
}

function agentStepToRuntimeStep(step: AgentStep, position: number): StepUpdate {
  return {
    step_id: `agent-${position}-${step.kind}-${step.tool_name ?? "model"}-${step.index}`,
    label: agentStepLabel(step),
    status: step.status === "error" ? "error" : "complete",
  };
}

const MAIL_READ_PATTERNS = [
  /\b(read|check|summari[sz]e|triage|review|scan)\s+(my\s+)?(mail|email|emails|inbox)\b/i,
  /\b(mail|email|emails|inbox)\s+(summary|brief|triage|priorit(?:y|ies)|unread|needs?\s+reply)\b/i,
  /\b(unread|recent|latest|today'?s?)\s+(mail|email|emails|inbox)\b/i,
  /\b(mail|email|emails)\s+(n[aà]o|c[aầ]n|ch[uư]a)\b/i,
  /\b(d[oọ]c|kiem tra|ki[eể]m tra|tom tat|t[oó]m t[aắ]t|loc|l[oọ]c)\s+(mail|email|inbox|hop thu|h[oộ]p th[uư])\b/i,
  /\b(mail|email|inbox|hop thu|h[oộ]p th[uư])\s+(chua doc|ch[uư]a [dđ]oc|ch[uư]a [dđ][oọ]c|can phan hoi|c[aầ]n ph[aả]n h[oồ]i|hom nay|h[oô]m nay)\b/i,
];

const EMAIL_WRITE_PATTERNS = [
  /\b(write|draft|compose|send|reply|respond|forward)\s+(an?\s+)?(mail|email|emails)\b/i,
  /\b(soan|so[aạ]n|gui|g[uử]i|tra loi|tr[aả] l[oờ]i|phan hoi|ph[aả]n h[oồ]i)\s+(mail|email)\b/i,
];

function stripVietnameseDiacritics(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[đĐ]/g, (match) => (match === "Đ" ? "D" : "d"));
}

function detectMailAgentIntent(prompt: string): boolean {
  const normalized = stripVietnameseDiacritics(prompt);
  if (EMAIL_WRITE_PATTERNS.some((pattern) => pattern.test(prompt) || pattern.test(normalized))) {
    return false;
  }
  return MAIL_READ_PATTERNS.some((pattern) => pattern.test(prompt) || pattern.test(normalized));
}

interface ChatShellProps {
  apiClient: ApiClient;
  conversationId: string;
  googleConfigured?: boolean;
  onNavigateConversation: (conversationId: string) => void;
}

export function ChatShell({
  apiClient,
  conversationId,
  googleConfigured = true,
  onNavigateConversation,
}: ChatShellProps) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationTitle, setConversationTitle] = useState("New chat");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isCreatingConversation, setIsCreatingConversation] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [liveSteps, setLiveSteps] = useState<StepUpdate[]>([]);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [liveSources, setLiveSources] = useState<SourceItem[]>([]);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const [messageModes, setMessageModes] = useState<Record<string, ChatStreamMode>>({});
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [gmailActionPending, setGmailActionPending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);
  const threadAnchorRef = useRef<HTMLDivElement | null>(null);
  const draftRef = useRef(draft);
  const isStreamingRef = useRef(isStreaming);
  const isCreatingConversationRef = useRef(false);
  const lastCreatedBlankConversationRef = useRef<ConversationSummary | null>(null);
  const deletingConversationIdsRef = useRef<Set<string>>(new Set());
  const [deletingConversationIds, setDeletingConversationIds] = useState<string[]>([]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  const refreshGmailStatus = useCallback(async () => {
    try {
      setGmailStatus(await apiClient.getGmailStatus());
    } catch {
      setGmailStatus({ connected: false, email: null, scopes: [] });
    }
  }, [apiClient]);

  const displayedSources = useMemo(
    () => (liveSources.length > 0 ? liveSources : latestAssistantSources(messages)),
    [liveSources, messages],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadConversation() {
      setIsLoading(true);
      setBanner(null);
      setLiveSteps([]);
      setAgentSteps([]);
      setLiveSources([]);
      try {
        const [conversationList, conversation] = await Promise.all([
          apiClient.listConversations(),
          apiClient.getConversation(conversationId),
        ]);
        if (cancelled) return;
        setConversations(sortConversationList(conversationList));
        setConversationTitle(conversation.title);
        setMessages(conversation.messages);
        setMessageModes({});
      } catch (cause) {
        if (!cancelled) {
          setBanner(cause instanceof Error ? cause.message : "Unable to load this conversation.");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadConversation();
    void refreshGmailStatus();

    return () => {
      cancelled = true;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, [apiClient, conversationId, refreshGmailStatus]);

  useEffect(() => {
    threadAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, liveSteps]);

  const createNewConversation = useCallback(async () => {
    if (isCreatingConversationRef.current) return;

    const activeConversation = conversations.find((item) => item.id === conversationId);
    const currentLooksBlank =
      isBlankConversation(activeConversation) ||
      (conversationTitle === DEFAULT_CONVERSATION_TITLE && messages.length === 0);
    if (currentLooksBlank) {
      setSidebarOpen(false);
      return;
    }

    const knownConversationIds = new Set(conversations.map((item) => item.id));
    const blankCandidates =
      lastCreatedBlankConversationRef.current &&
      !knownConversationIds.has(lastCreatedBlankConversationRef.current.id)
        ? [...conversations, lastCreatedBlankConversationRef.current]
        : conversations;
    const reusableBlankConversation = sortConversationList(blankCandidates).find(isBlankConversation);
    if (reusableBlankConversation) {
      setSidebarOpen(false);
      onNavigateConversation(reusableBlankConversation.id);
      return;
    }

    isCreatingConversationRef.current = true;
    setIsCreatingConversation(true);
    try {
      const conversation = await apiClient.createConversation();
      lastCreatedBlankConversationRef.current = conversation;
      setConversations((current) => upsertConversation(current, conversation));
      onNavigateConversation(conversation.id);
    } catch (cause) {
      setBanner(cause instanceof Error ? cause.message : "Unable to create a new conversation.");
    } finally {
      isCreatingConversationRef.current = false;
      setIsCreatingConversation(false);
      setSidebarOpen(false);
    }
  }, [apiClient, conversationId, conversationTitle, conversations, messages.length, onNavigateConversation]);

  const deleteActiveFallbackConversation = useCallback(
    async (remainingConversations: ConversationSummary[]) => {
      if (remainingConversations.length > 0) {
        onNavigateConversation(remainingConversations[0].id);
        return;
      }

      if (isCreatingConversationRef.current) return;
      isCreatingConversationRef.current = true;
      setIsCreatingConversation(true);
      try {
        const conversation = await apiClient.createConversation();
        lastCreatedBlankConversationRef.current = conversation;
        setConversations([conversation]);
        onNavigateConversation(conversation.id);
      } finally {
        isCreatingConversationRef.current = false;
        setIsCreatingConversation(false);
      }
    },
    [apiClient, onNavigateConversation],
  );

  const deleteConversation = useCallback(
    async (targetConversationId: string) => {
      if (deletingConversationIdsRef.current.has(targetConversationId)) return;

      const targetConversation = conversations.find((item) => item.id === targetConversationId);
      const confirmed = window.confirm(
        `Delete "${targetConversation?.title ?? "this chat"}"?`,
      );
      if (!confirmed) return;

      deletingConversationIdsRef.current.add(targetConversationId);
      setDeletingConversationIds((current) => [...current, targetConversationId]);
      setBanner(null);

      try {
        await apiClient.deleteConversation(targetConversationId);
        const remainingConversations = sortConversationList(
          conversations.filter((item) => item.id !== targetConversationId),
        );
        setConversations(remainingConversations);
        setSidebarOpen(false);

        if (targetConversationId === conversationId) {
          abortControllerRef.current?.abort();
          await deleteActiveFallbackConversation(remainingConversations);
        }
      } catch (cause) {
        setBanner(cause instanceof Error ? cause.message : "Unable to delete this conversation.");
      } finally {
        deletingConversationIdsRef.current.delete(targetConversationId);
        setDeletingConversationIds((current) =>
          current.filter((item) => item !== targetConversationId),
        );
      }
    },
    [
      apiClient,
      conversationId,
      conversations,
      deleteActiveFallbackConversation,
    ],
  );

  const sendMessage = useCallback(
    async (promptOverride?: string) => {
      const prompt = (promptOverride ?? draftRef.current).trim();
      if (!prompt || isStreamingRef.current) return;

      const mode: ChatStreamMode = detectMailAgentIntent(prompt) ? "agent" : "chat";
      const optimisticUser = createOptimisticMessage("user", prompt);
      const optimisticAssistant = createOptimisticMessage("assistant", "");
      const streamController = new AbortController();
      abortControllerRef.current = streamController;
      setDraft("");
      setLastPrompt(prompt);
      setBanner(null);
      setLiveSteps([]);
      setAgentSteps([]);
      setLiveSources([]);
      setIsStreaming(true);
      setMessages((current) => [...current, optimisticUser, optimisticAssistant]);
      setMessageModes((current) => ({ ...current, [optimisticAssistant.id]: mode }));
      setPanelOpen(true);

      let streamErrored = false;

      const updateAssistantMessage = (
        nextValue: UiMessage | ((current: UiMessage) => UiMessage),
      ) => {
        setMessages((current) =>
          current.map((message) => {
            if (message.id !== optimisticAssistant.id) return message;
            return typeof nextValue === "function" ? nextValue(message) : nextValue;
          }),
        );
      };

      const handleStreamEvent = (event: StreamEvent) => {
        switch (event.type) {
          case "message_start":
            setConversationTitle(event.payload.conversation.title);
            setConversations((current) => upsertConversation(current, event.payload.conversation));
            setMessages((current) =>
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
            updateAssistantMessage((current) => ({
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
            setLiveSources((current) => [...current, event.payload]);
            break;
          case "message_complete":
            setConversationTitle(event.payload.conversation.title);
            setConversations((current) => upsertConversation(current, event.payload.conversation));
            setMessageModes((current) => {
              const { [optimisticAssistant.id]: _removed, ...remaining } = current;
              return { ...remaining, [event.payload.assistant_message.id]: mode };
            });
            updateAssistantMessage({
              ...event.payload.assistant_message,
              pending: false,
            });
            break;
          case "error":
            streamErrored = true;
            setDraft(prompt);
            setBanner(event.payload.message);
            updateAssistantMessage((current) => ({
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
        const streamPayload =
          mode === "agent"
            ? { message: prompt, mode, max_steps: 5 }
            : { message: prompt, mode };
        await apiClient.streamConversationMessage(
          conversationId,
          streamPayload,
          { signal: streamController.signal, onEvent: handleStreamEvent },
        );
      } catch (cause) {
        if (streamController.signal.aborted) {
          setBanner("Generation stopped.");
          updateAssistantMessage((current) => ({ ...current, pending: false }));
        } else {
          const message = cause instanceof Error ? cause.message : "Unable to stream a response.";
          setDraft(prompt);
          setBanner(message);
          updateAssistantMessage((current) => ({
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
            current.map((step) => ({
              ...step,
              status: step.status === "error" ? step.status : "complete",
            })),
          );
        }
      }
    },
    [apiClient, conversationId],
  );

  const stopStreaming = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const openSidebar = useCallback(() => setSidebarOpen(true), []);
  const togglePanel = useCallback(() => setPanelOpen((current) => !current), []);
  const closePanel = useCallback(() => setPanelOpen(false), []);
  const handleGmailLogin = useCallback(() => {
    if (!googleConfigured) {
      setBanner("Google sign-in is not configured on this server.");
      return;
    }
    void signIn("google", { callbackUrl: window.location.href });
  }, [googleConfigured]);
  const handleGmailLogout = useCallback(async () => {
    setGmailActionPending(true);
    setBanner(null);
    try {
      setGmailStatus(await apiClient.disconnectGmail());
    } catch (cause) {
      setBanner(cause instanceof Error ? cause.message : "Unable to disconnect Gmail.");
    } finally {
      setGmailActionPending(false);
    }
  }, [apiClient]);

  const handleNewConversation = useCallback(() => {
    void createNewConversation();
  }, [createNewConversation]);

  const handleSelectConversation = useCallback(
    (nextConversationId: string) => {
      setSidebarOpen(false);
      onNavigateConversation(nextConversationId);
    },
    [onNavigateConversation],
  );

  const handleSend = useCallback(() => {
    void sendMessage();
  }, [sendMessage]);

  const handleRetry = useCallback(() => {
    void sendMessage(lastPrompt ?? undefined);
  }, [sendMessage, lastPrompt]);

  const handlePromptSelect = useCallback((prompt: string) => {
    setDraft(prompt);
  }, []);

  return (
    <div
      data-panel={panelOpen ? "open" : "closed"}
      className={`grid h-screen min-h-0 grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] ${
        panelOpen ? "xl:grid-cols-[280px_minmax(0,1fr)_360px]" : ""
      }`}
    >
      <ConversationSidebar
        activeConversationId={conversationId}
        conversations={conversations}
        isCreatingConversation={isCreatingConversation}
        open={sidebarOpen}
        onClose={closeSidebar}
        onDeleteConversation={deleteConversation}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
        deletingConversationIds={deletingConversationIds}
      />

      <main className="flex min-h-0 min-w-0 flex-col bg-bg-thread">
        {/* Mobile chrome */}
        <div className="flex items-center justify-between border-b border-line bg-bg-rail px-3 py-2 lg:hidden">
          <button
            type="button"
            onClick={openSidebar}
            aria-label="Open conversations"
            className="om-icon-btn"
          >
            <IconMenu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <span className="grid h-[22px] w-[22px] place-items-center rounded-md border border-accent-ring bg-accent-soft text-accent-fg">
              <IconModel size={12} />
            </span>
            <strong className="text-[13px]">Open Model</strong>
          </div>
          <button
            type="button"
            onClick={togglePanel}
            aria-label={panelOpen ? "Hide runtime panel" : "Show runtime panel"}
            aria-expanded={panelOpen}
            aria-controls="runtime-panel"
            className="om-icon-btn"
          >
            <IconPanel size={16} />
          </button>
        </div>

        {banner ? (
          <div
            role="alert"
            className="mx-6 mt-4 flex items-start gap-3 rounded-lg border border-warn-bd bg-warn-bg px-3.5 py-3 text-warn-fg"
          >
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-yellow-300/10">
              <IconAlert size={16} />
            </span>
            <div className="min-w-0 flex-1 text-[12.5px] leading-relaxed">{banner}</div>
            <button
              type="button"
              aria-label="Dismiss banner"
              onClick={() => setBanner(null)}
              className="om-icon-btn"
            >
              <span className="text-[12px] font-mono">×</span>
            </button>
          </div>
        ) : null}

        <div className="om-scroll flex min-h-0 flex-1 flex-col overflow-y-auto">
          <MessageThread
            canRetry={Boolean(lastPrompt)}
            isLoading={isLoading}
            liveSteps={liveSteps}
            messageModes={messageModes}
            messages={messages}
            onPromptSelect={handlePromptSelect}
            onRetry={handleRetry}
            title={conversationTitle}
          />
          <div ref={threadAnchorRef} />
        </div>

        <Composer
          canRetry={Boolean(lastPrompt)}
          disabled={isLoading}
          draft={draft}
          isStreaming={isStreaming}
          onDraftChange={setDraft}
          onRetry={handleRetry}
          onSend={handleSend}
          onStop={stopStreaming}
        />
      </main>

      <AgentStatusPanel
        steps={liveSteps}
        agentSteps={agentSteps}
        sources={displayedSources}
        isStreaming={isStreaming}
        gmailStatus={gmailStatus}
        gmailActionPending={gmailActionPending}
        open={panelOpen}
        onGmailLogin={handleGmailLogin}
        onGmailLogout={handleGmailLogout}
        onToggle={togglePanel}
        onClose={closePanel}
      />
    </div>
  );
}
