import { memo, useEffect, useRef } from "react";

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
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [draft]);

  return (
    <div className="sticky bottom-0 z-10 border-t border-stroke-subtle bg-surface-base px-3 pb-3 pt-3 sm:px-6 sm:pb-4">
      <div className="app-surface-strong rounded-[18px] p-3 sm:p-4">
        <div className="flex items-center justify-between gap-3">
          <label className="app-meta text-content-secondary" htmlFor="message-composer">
            Prompt
          </label>
          <p className="hidden text-xs text-content-secondary sm:block">Enter to send</p>
        </div>

        <textarea
          ref={textareaRef}
          id="message-composer"
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          rows={2}
          placeholder="Ask a question, summarize, compare, or stage the next task."
          className="app-focus-ring mt-3 max-h-[13.75rem] min-h-[4.75rem] w-full resize-none rounded-[12px] border border-transparent bg-transparent px-0 py-0 text-[15px] leading-7 text-content-primary outline-none placeholder:text-content-secondary"
          disabled={disabled}
        />

        <div className="mt-3 flex flex-col gap-3 border-t border-stroke-subtle pt-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-content-secondary sm:text-sm">Shift + Enter adds a new line.</p>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onRetry}
              disabled={!canRetry || isStreaming}
              className="app-button app-button-secondary app-focus-ring text-sm font-medium"
            >
              Retry
            </button>
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                className="app-button app-button-danger app-focus-ring text-sm font-semibold"
              >
                Stop
              </button>
            ) : (
              <button
                type="button"
                onClick={onSend}
                disabled={disabled || draft.trim().length === 0}
                className="app-button app-button-primary app-focus-ring text-sm font-semibold"
              >
                Send
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export const Composer = memo(ComposerImpl);
