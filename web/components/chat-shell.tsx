"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentStatusPanel } from "@/components/agent-status-panel";
import { Composer } from "@/components/composer";
import { ConversationSidebar } from "@/components/conversation-sidebar";
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

function upsertConversation(items: ConversationSummary[], nextConversation: ConversationSummary): ConversationSummary[] {
  const remaining = items.filter((item) => item.id !== nextConversation.id);
  return sortConversationList([nextConversation, ...remaining]);
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
  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant" && message.sources.length > 0);
  return latestAssistant?.sources ?? [];
}

function MenuIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4">
      <path d="M3.5 6h13M3.5 10h13M3.5 14h13" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function PanelIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4">
      <path d="M4 4.5h12a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1Zm8 0v11" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  );
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
  const [panelOpen, setPanelOpen] = useState(false);
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
        if (cancelled) {
          return;
        }
        setConversations(sortConversationList(conversationList));
        setConversationTitle(conversation.title);
        setMessages(conversation.messages);
      } catch (cause) {
        if (!cancelled) {
          setBanner(cause instanceof Error ? cause.message : "Unable to load this conversation.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
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

  const sendMessage = useCallback(async (promptOverride?: string) => {
    const prompt = (promptOverride ?? draftRef.current).trim();
    if (!prompt || isStreamingRef.current) {
      return;
    }

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

    const updateAssistantMessage = (nextValue: UiMessage | ((current: UiMessage) => UiMessage)) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== optimisticAssistant.id) {
            return message;
          }
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
            current.map((message) => (message.id === optimisticUser.id ? { ...event.payload.user_message } : message)),
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
        {
          message: prompt,
          mode: "chat",
        },
        {
          signal: streamController.signal,
          onEvent: handleStreamEvent,
        },
      );
    } catch (cause) {
      if (streamController.signal.aborted) {
        setBanner("Generation stopped.");
        updateAssistantMessage((current) => ({
          ...current,
          pending: false,
        }));
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
  }, [apiClient, conversationId]);

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
    <main className="min-h-screen px-3 py-3 text-content-primary sm:px-4">
      <div className="mx-auto grid min-h-[calc(100vh-1.5rem)] max-w-[1720px] grid-cols-1 gap-3 lg:grid-cols-[17.5rem_minmax(0,1fr)] xl:grid-cols-[17.5rem_minmax(0,1fr)_22rem]">
        <ConversationSidebar
          activeConversationId={conversationId}
          conversations={conversations}
          isCreatingConversation={isCreatingConversation}
          open={sidebarOpen}
          onClose={closeSidebar}
          onNewConversation={handleNewConversation}
          onSelectConversation={handleSelectConversation}
        />

        <section className="app-surface flex min-w-0 flex-col overflow-hidden rounded-[24px]">
          <header className="flex items-start justify-between gap-4 border-b border-stroke-subtle px-4 py-4 sm:px-6 sm:py-5">
            <div className="flex items-start gap-3">
              <button
                type="button"
                onClick={openSidebar}
                aria-label="Open conversations"
                className="app-icon-button app-button-secondary app-focus-ring shrink-0 lg:hidden"
              >
                <MenuIcon />
              </button>

              <div>
                <p className="app-meta text-content-secondary">Open Model</p>
                <h1 className="mt-3 text-lg font-semibold tracking-tight text-content-primary sm:text-xl">
                  Local chat workspace
                </h1>
              </div>
            </div>

            <button
              type="button"
              onClick={togglePanel}
              className="app-button app-button-secondary app-focus-ring shrink-0 px-3 text-sm font-medium xl:hidden"
              aria-label={panelOpen ? "Hide runtime panel" : "Show runtime panel"}
              aria-expanded={panelOpen}
              aria-controls="runtime-panel"
            >
              <PanelIcon />
              <span className="hidden sm:inline">{panelOpen ? "Hide runtime" : "Runtime"}</span>
            </button>
          </header>

          {banner ? (
            <div
              role="alert"
              className="mx-4 mt-4 rounded-[16px] border border-warning-border bg-warning-bg px-4 py-3 text-sm text-warning-fg sm:mx-6"
            >
              {banner}
            </div>
          ) : null}

          <div className="app-shell-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto">
            <MessageThread
              isLoading={isLoading}
              liveSteps={liveSteps}
              messages={messages}
              onPromptSelect={handlePromptSelect}
              title={conversationTitle}
            />
            <div ref={threadAnchorRef} />
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
          </div>
        </section>

        <AgentStatusPanel
          open={panelOpen}
          onClose={closePanel}
          sources={displayedSources}
          steps={liveSteps}
        />
      </div>
    </main>
  );
}
