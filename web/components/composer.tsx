import { memo } from "react";

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
  return (
    <div className="sticky bottom-0 z-10 border-t border-stroke-subtle bg-surface-base px-4 pb-4 pt-4 sm:px-6">
      <div className="app-surface-strong rounded-[20px] p-4">
        <label className="app-meta text-content-secondary" htmlFor="message-composer">
          Prompt
        </label>

        <textarea
          id="message-composer"
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          rows={4}
          placeholder="Ask a question, request a summary, or stage the next task."
          className="app-focus-ring mt-3 min-h-[7.25rem] w-full rounded-[16px] border border-transparent bg-transparent px-0 py-0 text-[15px] leading-7 text-content-primary outline-none placeholder:text-content-secondary"
          disabled={disabled}
        />

        <div className="mt-4 flex flex-col gap-4 border-t border-stroke-subtle pt-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-content-primary">Enter sends. Shift + Enter adds a new line.</p>
            <p className="mt-1 text-sm text-content-secondary">Responses stream directly from the local runtime.</p>
          </div>

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
