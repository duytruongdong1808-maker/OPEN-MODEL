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

export function ConversationSidebar({
  conversations,
  activeConversationId,
  isCreatingConversation,
  open,
  onClose,
  onNewConversation,
  onSelectConversation,
}: ConversationSidebarProps) {
  const sidebarClasses = open
    ? "pointer-events-auto translate-x-0 opacity-100"
    : "pointer-events-none -translate-x-6 opacity-0 lg:pointer-events-auto lg:translate-x-0 lg:opacity-100";

  return (
    <>
      <div
        aria-hidden={!open}
        className={`fixed inset-0 z-20 bg-shell-900/20 backdrop-blur-sm transition lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />
      <aside
        className={`app-shell-scrollbar fixed inset-y-4 left-4 z-30 flex w-[min(19rem,calc(100vw-2rem))] flex-col overflow-y-auto rounded-[2rem] border border-black/5 bg-[var(--panel-bg)] p-5 shadow-shell backdrop-blur lg:static lg:inset-auto lg:w-[18rem] lg:translate-x-0 lg:opacity-100 ${sidebarClasses}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.34em] text-accent-700">Open Model</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-shell-900">Chat workspace</h1>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/5 px-3 py-2 text-xs font-medium text-shell-600 transition hover:border-shell-300 hover:text-shell-900 lg:hidden"
          >
            Close
          </button>
        </div>

        <button
          type="button"
          onClick={onNewConversation}
          className="mt-6 rounded-3xl bg-accent-500 px-4 py-3 text-left text-sm font-semibold text-white shadow-lg shadow-accent-500/20 transition hover:bg-accent-700"
        >
          {isCreatingConversation ? "Creating a new thread…" : "New chat"}
        </button>

        <div className="mt-8">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm font-semibold text-shell-900">Recent conversations</p>
            <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-shell-500">
              {conversations.length}
            </span>
          </div>

          <div className="space-y-2">
            {conversations.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-shell-300/80 bg-white/40 px-4 py-5 text-sm text-shell-600">
                Start a thread to build your workspace history.
              </div>
            ) : (
              conversations.map((conversation) => {
                const isActive = conversation.id === activeConversationId;

                return (
                  <button
                    key={conversation.id}
                    type="button"
                    onClick={() => onSelectConversation(conversation.id)}
                    className={`w-full rounded-3xl px-4 py-4 text-left transition ${
                      isActive
                        ? "border border-accent-500/20 bg-accent-100/70 shadow-sm"
                        : "border border-transparent bg-white/45 hover:border-black/5 hover:bg-white/70"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-shell-900">{conversation.title}</p>
                      <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-shell-500">
                        {formatConversationTime(conversation.updated_at)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-shell-600">
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
