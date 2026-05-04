"use client";

import { memo, useEffect, useRef } from "react";

import type { ChatStreamMode } from "@/lib/types";

import {
  IconCpu,
  IconMail,
  IconModel,
  IconRetry,
  IconSend,
  IconStop,
} from "@/components/ui/icons";

type ComposerMode = Extract<ChatStreamMode, "chat" | "agent">;

interface ComposerProps {
  draft: string;
  disabled: boolean;
  isStreaming: boolean;
  canRetry: boolean;
  selectedMode: ComposerMode;
  effectiveMode: ComposerMode;
  onDraftChange: (value: string) => void;
  onModeChange: (mode: ComposerMode) => void;
  onSend: () => void;
  onStop: () => void;
  onRetry: () => void;
}

function ComposerImpl({
  draft,
  disabled,
  isStreaming,
  canRetry,
  selectedMode,
  effectiveMode,
  onDraftChange,
  onModeChange,
  onSend,
  onStop,
  onRetry,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, [draft]);

  const canSend = draft.trim().length > 0 && !isStreaming && !disabled;
  const autoMailAgent = selectedMode === "chat" && effectiveMode === "agent";

  return (
    <div className="shrink-0 px-4 pt-2.5 pb-4 sm:px-6 [background:linear-gradient(180deg,transparent,var(--bg-thread)_30%)]">
      <div className="mx-auto max-w-[800px] rounded-xl border border-line-strong bg-bg-input p-3.5 pb-2.5 shadow-soft transition-all focus-within:border-accent-ring focus-within:[box-shadow:0_0_0_3px_var(--accent-soft),0_0_40px_var(--accent-glow),var(--shadow-soft)]">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div
            role="radiogroup"
            aria-label="Chat mode"
            className="inline-flex rounded-lg border border-line bg-bg-rail p-1"
          >
            {(["chat", "agent"] as const).map((mode) => {
              const active = selectedMode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => onModeChange(mode)}
                  disabled={disabled || isStreaming}
                  className={`om-focus inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11.5px] font-semibold transition ${
                    active
                      ? "bg-accent-solid text-[#071014] shadow-[0_0_18px_var(--accent-glow)]"
                      : "text-text-3 hover:bg-bg-raised hover:text-text"
                  }`}
                >
                  {mode === "chat" ? <IconModel size={13} /> : <IconMail size={13} />}
                  {mode === "chat" ? "Chat" : "Mail agent"}
                </button>
              );
            })}
          </div>
          <span className="rounded-full border border-line bg-bg-raised px-2.5 py-1 font-mono text-[10.5px] text-text-3">
            {autoMailAgent
              ? "Auto: Mail agent"
              : effectiveMode === "agent"
                ? "Read-only mail"
                : "Local chat"}
          </span>
        </div>

        <textarea
          ref={textareaRef}
          data-testid="composer-input"
          id="message-composer"
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (canSend) onSend();
            }
          }}
          rows={1}
          disabled={disabled}
          placeholder={
            isStreaming
              ? "Generating response - press Stop to interrupt"
              : "Ask anything. Shift + Enter for new line."
          }
          aria-label="Message"
          className="block max-h-[200px] min-h-[28px] w-full resize-none border-0 bg-transparent px-0 py-1 text-[14.5px] leading-snug text-text outline-none placeholder:text-text-4"
        />

        <div className="mt-2.5 flex items-center justify-between gap-2.5">
          <div className="flex flex-wrap items-center gap-1">
            <span className="om-chip">
              <IconCpu size={12} /> {effectiveMode === "agent" ? "Mail agent" : "Local chat"}
            </span>
            {autoMailAgent && (
              <span className="om-chip border-accent-ring bg-accent-soft text-accent-fg">
                Inbox intent detected
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {canRetry && !isStreaming && (
              <button type="button" onClick={onRetry} className="om-btn om-btn-ghost">
                <IconRetry size={14} /> Retry
              </button>
            )}
            {isStreaming ? (
              <button type="button" onClick={onStop} className="om-btn om-btn-stop">
                <IconStop size={13} /> Stop
              </button>
            ) : (
              <button
                type="button"
                data-testid="composer-submit"
                onClick={onSend}
                disabled={!canSend}
                className="om-btn om-btn-send disabled:opacity-40"
              >
                Send <IconSend size={13} />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="mx-auto mt-2 flex max-w-[800px] justify-between gap-3 font-mono text-[10.5px] text-text-4">
        <span>
          <span className="om-kbd">Enter</span> send · <span className="om-kbd">Shift Enter</span>{" "}
          newline
        </span>
        <span className="inline-flex items-center gap-1.5">
          <IconCpu size={11} /> running on-device · no telemetry
        </span>
      </div>
    </div>
  );
}

export const Composer = memo(ComposerImpl);
