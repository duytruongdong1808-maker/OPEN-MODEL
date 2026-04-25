"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentStatusPanel } from "@/components/agent-status-panel";
import { Composer } from "@/components/composer";
import { ConversationSidebar } from "@/components/conversation-sidebar";
import { IconAlert, IconMenu, IconModel, IconPanel } from "@/components/icons";
import { MessageThread } from "@/components/message-thread";
import type { ApiClient } from "@/lib/api";
import type {
  ConversationSummary,
  SourceItem,
  StreamEvent,
  StepUpdate,
  UiMessage,
} from "@/lib/types";

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

interface ChatShellProps {
  apiClient: ApiClient;
  conversationId: string;
  onNavigateConversation: (conversationId: string) => void;
}

export function ChatShell({
  apiClient,
  conversationId,
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
  const [liveSources, setLiveSources] = useState<SourceItem[]>([]);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);
  const threadAnchorRef = useRef<HTMLDivElement | null>(null);
  const draftRef = useRef(draft);
  const isStreamingRef = useRef(isStreaming);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

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
      } catch (cause) {
        if (!cancelled) {
          setBanner(cause instanceof Error ? cause.message : "Unable to load this conversation.");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadConversation();

    return () => {
      cancelled = true;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, [apiClient, conversationId]);

  useEffect(() => {
    threadAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, liveSteps]);

  const createNewConversation = useCallback(async () => {
    setIsCreatingConversation(true);
    try {
      const conversation = await apiClient.createConversation();
      setConversations((current) => upsertConversation(current, conversation));
      onNavigateConversation(conversation.id);
    } catch (cause) {
      setBanner(cause instanceof Error ? cause.message : "Unable to create a new conversation.");
    } finally {
      setIsCreatingConversation(false);
      setSidebarOpen(false);
    }
  }, [apiClient, onNavigateConversation]);

  const sendMessage = useCallback(
    async (promptOverride?: string) => {
      const prompt = (promptOverride ?? draftRef.current).trim();
      if (!prompt || isStreamingRef.current) return;

      const optimisticUser = createOptimisticMessage("user", prompt);
      const optimisticAssistant = createOptimisticMessage("assistant", "");
      const streamController = new AbortController();
      abortControllerRef.current = streamController;
      setDraft("");
      setLastPrompt(prompt);
      setBanner(null);
      setLiveSteps([]);
      setLiveSources([]);
      setIsStreaming(true);
      setMessages((current) => [...current, optimisticUser, optimisticAssistant]);
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
          case "source_add":
            setLiveSources((current) => [...current, event.payload]);
            break;
          case "message_complete":
            setConversationTitle(event.payload.conversation.title);
            setConversations((current) => upsertConversation(current, event.payload.conversation));
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
        await apiClient.streamConversationMessage(
          conversationId,
          { message: prompt, mode: "chat" },
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
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
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
            isLoading={isLoading}
            liveSteps={liveSteps}
            messages={messages}
            onPromptSelect={handlePromptSelect}
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
        sources={displayedSources}
        isStreaming={isStreaming}
        open={panelOpen}
        onToggle={togglePanel}
        onClose={closePanel}
      />
    </div>
  );
}
