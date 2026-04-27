"use client";

import { memo, useEffect, useMemo, useState } from "react";
import { signOut } from "next-auth/react";

import { formatConversationTime, truncatePreview } from "@/lib/format";
import type { ConversationSummary } from "@/lib/types";

import {
  IconModel,
  IconLogOut,
  IconPlus,
  IconSearch,
  IconTrash,
  IconUser,
  IconX,
} from "./icons";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  activeConversationId: string;
  isCreatingConversation: boolean;
  open: boolean;
  onClose: () => void;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
  deletingConversationIds?: string[];
}

function groupConversations(items: ConversationSummary[]) {
  const now = Date.now();
  const day = 86_400_000;
  const today: ConversationSummary[] = [];
  const yesterday: ConversationSummary[] = [];
  const earlier: ConversationSummary[] = [];
  for (const c of items) {
    const updated = new Date(c.updated_at).getTime();
    const age = now - (Number.isNaN(updated) ? now : updated);
    if (age < day) today.push(c);
    else if (age < day * 2) yesterday.push(c);
    else earlier.push(c);
  }
  return { Today: today, Yesterday: yesterday, Earlier: earlier };
}

function ConversationSidebarImpl({
  conversations,
  activeConversationId,
  isCreatingConversation,
  open,
  onClose,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
  deletingConversationIds = [],
}: ConversationSidebarProps) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    if (!query.trim()) return conversations;
    const q = query.toLowerCase();
    return conversations.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        (c.last_message_preview ?? "").toLowerCase().includes(q),
    );
  }, [conversations, query]);

  const groups = useMemo(() => groupConversations(filtered), [filtered]);

  return (
    <>
      <div
        aria-hidden={!open}
        className={`fixed inset-0 z-20 bg-black/60 backdrop-blur-[2px] transition lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
      />

      <aside
        aria-label="Conversations"
        className={`om-scroll fixed inset-y-0 left-0 z-30 flex w-[min(320px,86vw)] flex-col overflow-y-auto border-r border-line bg-bg-rail transition-transform lg:sticky lg:top-0 lg:h-screen lg:w-full lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        {/* Brand row */}
        <div className="flex items-center gap-2.5 border-b border-line px-3.5 py-3.5">
          <div className="flex flex-1 items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-[9px] border border-accent-ring bg-accent-soft text-accent-fg">
              <IconModel size={15} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] font-semibold tracking-tight text-text">Open Model</div>
              <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[10.5px] text-text-3">
                <span
                  className="h-1.5 w-1.5 rounded-full bg-accent-solid"
                  style={{ boxShadow: "0 0 0 3px var(--accent-glow)" }}
                />
                Local · on-device
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close conversations"
            className="om-icon-btn om-focus lg:hidden"
          >
            <IconX size={16} />
          </button>
        </div>

        {/* New chat */}
        <button
          type="button"
          data-testid="new-conversation"
          aria-label="Create new chat"
          onClick={onNewConversation}
          className="om-focus mx-3 mt-3 flex items-center gap-2.5 rounded-md border border-line-strong bg-bg-raised px-3 py-2.5 text-left text-[13px] font-medium text-text transition-colors hover:border-accent-ring hover:bg-bg-emph"
        >
          <span className="grid h-[22px] w-[22px] place-items-center rounded-md border border-accent-ring bg-accent-soft text-accent-fg">
            <IconPlus size={15} />
          </span>
          <span className="flex-1">{isCreatingConversation ? "Creating thread…" : "New chat"}</span>
          <span className="om-kbd">⌘ K</span>
        </button>

        {/* Search */}
        <div className="mx-3 mt-3 mb-2 flex items-center gap-2 rounded-[9px] border border-line bg-bg-input px-2.5 py-2 text-text-3">
          <IconSearch size={14} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search conversations"
            aria-label="Search conversations"
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-text outline-none placeholder:text-text-4"
          />
        </div>

        {/* List */}
        <div className="om-scroll flex-1 overflow-y-auto px-2 pt-1 pb-3">
          {Object.entries(groups).map(([label, items]) =>
            items.length === 0 ? null : (
              <div key={label} className="mt-3.5 first:mt-1.5">
                <div className="px-2 pb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-text-4">
                  {label}
                </div>
                <ul className="flex flex-col gap-0.5">
                  {items.map((conversation) => {
                    const isActive = conversation.id === activeConversationId;
                    const isDeleting = deletingConversationIds.includes(conversation.id);
                    return (
                      <li key={conversation.id}>
                        <div
                          data-testid="conversation-item"
                          data-active={isActive ? "true" : "false"}
                          data-conversation-id={conversation.id}
                          className={`group relative flex w-full items-stretch rounded-[9px] border transition-colors ${
                            isActive
                              ? "border-line-strong bg-bg-raised"
                              : "border-transparent hover:bg-white/[0.03]"
                          }`}
                        >
                          {isActive && (
                            <span className="absolute -left-px top-2.5 bottom-2.5 w-0.5 rounded bg-accent-fg" />
                          )}
                          <button
                            type="button"
                            aria-current={isActive ? "page" : undefined}
                            aria-label={`Open ${conversation.title}`}
                            onClick={() => onSelectConversation(conversation.id)}
                            className="om-focus min-w-0 flex-1 rounded-l-[9px] px-2.5 py-2.5 text-left"
                          >
                            <div className="flex items-baseline gap-2">
                              <span className="flex-1 truncate text-[13px] font-medium text-text">
                                {conversation.title}
                              </span>
                              <span className="shrink-0 font-mono text-[10px] text-text-4">
                                {formatConversationTime(conversation.updated_at)}
                              </span>
                            </div>
                            <div className="mt-0.5 line-clamp-1 text-xs text-text-3">
                              {truncatePreview(conversation.last_message_preview)}
                            </div>
                          </button>
                          <button
                            type="button"
                            aria-label={`Delete ${conversation.title}`}
                            disabled={isDeleting}
                            onClick={() => onDeleteConversation(conversation.id)}
                            className="om-focus mr-1 my-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-text-4 opacity-70 transition hover:bg-warn-bg hover:text-warn-fg hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-50 focus:opacity-100"
                          >
                            <IconTrash size={14} />
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ),
          )}
          {filtered.length === 0 && (
            <div className="px-3 py-4 text-center text-[12.5px] text-text-3">
              No threads match “{query}”
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-line p-2.5">
          <div className="flex items-center gap-2.5 rounded-[10px] p-2 hover:bg-white/[0.03]">
            <div className="grid h-7 w-7 place-items-center rounded-full border border-line-strong bg-bg-emph text-text-2">
              <IconUser size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-medium text-text">Local workspace</div>
              <div className="font-mono text-[10px] text-text-3">on-device · 0 keys</div>
            </div>
            <button
              type="button"
              aria-label="Sign out"
              onClick={() => void signOut({ callbackUrl: "/login" })}
              className="om-icon-btn om-focus"
            >
              <IconLogOut size={14} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

export const ConversationSidebar = memo(ConversationSidebarImpl);
