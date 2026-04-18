"use client";

import { useEffect, useRef, useState } from "react";

import { AgentStatusPanel } from "@/components/agent-status-panel";
import { Composer } from "@/components/composer";
import { ConversationSidebar } from "@/components/conversation-sidebar";
import { MessageThread } from "@/components/message-thread";
import type { ApiClient } from "@/lib/api";
import type {
  ChatMessage,
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

  const displayedSources = liveSources.length > 0 ? liveSources : latestAssistantSources(messages);

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

  async function createNewConversation() {
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
  }

  async function sendMessage(promptOverride?: string) {
    const prompt = (promptOverride ?? draft).trim();
    if (!prompt || isStreaming) {
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
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
  }

  return (
    <main className="min-h-screen p-4">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-[1680px] gap-4">
        <ConversationSidebar
          activeConversationId={conversationId}
          conversations={conversations}
          isCreatingConversation={isCreatingConversation}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewConversation={() => void createNewConversation()}
          onSelectConversation={(nextConversationId) => {
            setSidebarOpen(false);
            onNavigateConversation(nextConversationId);
          }}
        />

        <section className="flex min-w-0 flex-1 flex-col rounded-[2rem] border border-black/5 bg-white/45 shadow-shell backdrop-blur">
          <header className="flex items-center justify-between gap-3 border-b border-black/5 px-4 py-4 sm:px-8">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                className="rounded-full border border-black/5 px-3 py-2 text-sm font-medium text-shell-700 transition hover:border-shell-300 hover:text-shell-900 lg:hidden"
              >
                Threads
              </button>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-shell-500">Open Model chat</p>
                <p className="mt-1 text-sm text-shell-600">
                  Internal shell for local chat today and a news agent tomorrow.
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setPanelOpen((current) => !current)}
              className="rounded-full border border-black/5 px-4 py-2 text-sm font-medium text-shell-700 transition hover:border-shell-300 hover:text-shell-900 xl:hidden"
            >
              {panelOpen ? "Hide sources panel" : "Show sources panel"}
            </button>
          </header>

          {banner ? (
            <div className="mx-4 mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 sm:mx-8">
              {banner}
            </div>
          ) : null}

          <div className="flex min-h-0 flex-1 flex-col">
            <MessageThread
              isLoading={isLoading}
              liveSteps={liveSteps}
              messages={messages}
              title={conversationTitle}
            />
            <div ref={threadAnchorRef} />
            <Composer
              canRetry={Boolean(lastPrompt)}
              disabled={isLoading}
              draft={draft}
              isStreaming={isStreaming}
              onDraftChange={setDraft}
              onRetry={() => void sendMessage(lastPrompt ?? undefined)}
              onSend={() => void sendMessage()}
              onStop={stopStreaming}
            />
          </div>
        </section>

      </div>

      <AgentStatusPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        sources={displayedSources}
        steps={liveSteps}
      />
    </main>
  );
}
