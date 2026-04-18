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

export function Composer({
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
    <div className="sticky bottom-0 z-10 bg-gradient-to-t from-[var(--page-bg)] via-[var(--page-bg)] to-transparent px-4 pb-4 pt-8 sm:px-8">
      <div className="rounded-[2rem] border border-black/5 bg-white/85 p-4 shadow-shell backdrop-blur">
        <textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          rows={4}
          placeholder="Ask a question, request a summary, or prepare this shell for news-agent work."
          className="min-h-[7rem] w-full border-none bg-transparent text-[15px] leading-7 text-shell-900 outline-none placeholder:text-shell-400"
          disabled={disabled}
        />

        <div className="mt-4 flex flex-col gap-4 border-t border-black/5 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-shell-800">Shift + Enter adds a new line.</p>
            <p className="mt-1 text-sm text-shell-500">
              The assistant streams directly from the local FastAPI runtime.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onRetry}
              disabled={!canRetry || isStreaming}
              className="rounded-full border border-shell-300 bg-white px-4 py-2 text-sm font-medium text-shell-700 transition hover:border-shell-500 hover:text-shell-900 disabled:cursor-not-allowed disabled:opacity-45"
            >
              Retry
            </button>
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                className="rounded-full border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 transition hover:border-rose-300 hover:bg-rose-100"
              >
                Stop
              </button>
            ) : (
              <button
                type="button"
                onClick={onSend}
                disabled={disabled || draft.trim().length === 0}
                className="rounded-full bg-accent-500 px-5 py-2 text-sm font-semibold text-white transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:bg-shell-300"
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
