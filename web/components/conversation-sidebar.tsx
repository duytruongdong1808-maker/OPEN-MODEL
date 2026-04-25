import { memo, useEffect } from "react";

import { formatConversationTime, truncatePreview } from "@/lib/format";
import type { ConversationSummary } from "@/lib/types";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  activeConversationId: string;
  isCreatingConversation: boolean;
  open: boolean;
  onClose: () => void;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
}

function ConversationSidebarImpl({
  conversations,
  activeConversationId,
  isCreatingConversation,
  open,
  onClose,
  onNewConversation,
  onSelectConversation,
}: ConversationSidebarProps) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  const sidebarClasses = open
    ? "pointer-events-auto translate-x-0 opacity-100"
    : "pointer-events-none -translate-x-6 opacity-0 lg:pointer-events-auto lg:translate-x-0 lg:opacity-100";

  return (
    <>
      <div
        aria-hidden={!open}
        className={`fixed inset-0 z-20 bg-overlay transition lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />

      <aside
        aria-label="Conversations"
        className={`app-shell-scrollbar app-surface fixed inset-y-3 left-3 z-30 flex w-[min(19rem,calc(100vw-1.5rem))] flex-col overflow-y-auto rounded-[24px] p-5 transition lg:sticky lg:top-3 lg:h-[calc(100vh-1.5rem)] lg:w-full lg:translate-x-0 lg:opacity-100 ${sidebarClasses}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="app-meta text-content-secondary">Open Model</p>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-content-primary">Workspace</h1>
            <p className="mt-2 text-sm leading-6 text-content-secondary">
              Manage threads and reopen recent context without leaving the main surface.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close conversations"
            className="app-icon-button app-button-secondary app-focus-ring lg:hidden"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4">
              <path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
            </svg>
          </button>
        </div>

        <button
          type="button"
          onClick={onNewConversation}
          className="app-button app-button-primary app-focus-ring mt-6 w-full justify-center px-4 py-3 text-sm font-semibold"
        >
          {isCreatingConversation ? "Creating thread..." : "New chat"}
        </button>

        <div className="mt-8 border-t border-stroke-subtle pt-6">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm font-semibold text-content-primary">Recent conversations</p>
            <span className="app-meta text-content-secondary">{conversations.length}</span>
          </div>

          <div className="space-y-2">
            {conversations.length === 0 ? (
              <div className="rounded-[16px] border border-dashed border-stroke-strong bg-interactive-hover px-4 py-5 text-sm leading-6 text-content-secondary">
                No conversation history yet. Start a thread to create a persistent workspace log.
              </div>
            ) : (
              conversations.map((conversation) => {
                const isActive = conversation.id === activeConversationId;

                return (
                  <button
                    key={conversation.id}
                    type="button"
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => onSelectConversation(conversation.id)}
                    className={`app-focus-ring w-full rounded-[18px] border px-4 py-4 text-left transition ${
                      isActive
                        ? "border-interactive-border bg-interactive-active"
                        : "border-transparent bg-transparent hover:border-stroke-subtle hover:bg-interactive-hover"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-content-primary">{conversation.title}</p>
                      <span className="text-xs uppercase tracking-[0.18em] text-content-secondary">
                        {formatConversationTime(conversation.updated_at)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-content-secondary">
                      {truncatePreview(conversation.last_message_preview)}
                    </p>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </aside>
    </>
  );
}

export const ConversationSidebar = memo(ConversationSidebarImpl);
