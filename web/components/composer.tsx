"use client";

import { memo, useEffect, useRef } from "react";

import {
  IconCpu,
  IconDoc,
  IconGlobe,
  IconRetry,
  IconSend,
  IconStop,
} from "./icons";

interface ComposerProps {
  draft: string;
  disabled: boolean;
  isStreaming: boolean;
  canRetry: boolean;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  onRetry: () => void;
}

function ComposerImpl({
  draft,
  disabled,
  isStreaming,
  canRetry,
  onDraftChange,
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

  return (
    <div className="shrink-0 px-6 pt-2.5 pb-4 [background:linear-gradient(180deg,transparent,var(--bg-thread)_30%)]">
      <div className="mx-auto max-w-[760px] rounded-xl border border-line-strong bg-bg-input p-3.5 pb-2.5 shadow-soft transition-all focus-within:border-accent-ring focus-within:[box-shadow:0_0_0_3px_var(--accent-soft),var(--shadow-soft)]">
        <textarea
          ref={textareaRef}
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
              ? "Generating response — press Stop to interrupt"
              : "Ask anything. Shift + Enter for new line."
          }
          aria-label="Message"
          className="block max-h-[200px] min-h-[28px] w-full resize-none border-0 bg-transparent px-0 py-1 text-[14.5px] leading-snug text-text outline-none placeholder:text-text-4"
        />

        <div className="mt-2.5 flex items-center justify-between gap-2.5">
          <div className="flex flex-wrap items-center gap-1">
            <button
              type="button"
              aria-label="Attach"
              className="grid h-7 w-7 place-items-center rounded-md text-text-3 transition-colors hover:bg-bg-raised hover:text-text"
            >
              <IconDoc size={15} />
            </button>
            <button
              type="button"
              aria-label="Search the web"
              className="grid h-7 w-7 place-items-center rounded-md text-text-3 transition-colors hover:bg-bg-raised hover:text-text"
            >
              <IconGlobe size={15} />
            </button>
            <span className="mx-1 h-4 w-px bg-line" />
            <span className="om-chip">
              <IconCpu size={12} /> Llama-3.1-70B
            </span>
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

      <div className="mx-auto mt-2 flex max-w-[760px] justify-between gap-3 font-mono text-[10.5px] text-text-4">
        <span>
          <span className="om-kbd">↵</span> send · <span className="om-kbd">⇧↵</span> newline
        </span>
        <span className="inline-flex items-center gap-1.5">
          <IconCpu size={11} /> running on-device · no telemetry
        </span>
      </div>
    </div>
  );
}

export const Composer = memo(ComposerImpl);
