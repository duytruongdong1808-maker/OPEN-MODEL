import { memo } from "react";

import type { StepUpdate, UiMessage } from "@/lib/types";

interface MessageThreadProps {
  title: string;
  messages: UiMessage[];
  liveSteps: StepUpdate[];
  isLoading: boolean;
  onPromptSelect: (prompt: string) => void;
}

const promptStarters = [
  "Summarize the latest context",
  "List the next best actions",
  "Compare the available sources",
];

function statusTone(step: StepUpdate): string {
  if (step.status === "active") {
    return "border-interactive-border bg-interactive-active text-content-tertiary";
  }
  if (step.status === "complete") {
    return "border-success-border bg-success-bg text-success-fg";
  }
  if (step.status === "error") {
    return "border-error-border bg-error-bg text-error-fg";
  }
  return "border-stroke-subtle bg-action-muted text-content-secondary";
}

function MessageThreadImpl({
  title,
  messages,
  liveSteps,
  isLoading,
  onPromptSelect,
}: MessageThreadProps) {
  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="max-w-md text-center">
          <p className="app-meta text-content-secondary">Syncing thread</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-content-primary">
            Loading conversation
          </h2>
          <p className="mt-3 text-sm leading-6 text-content-secondary">
            Restoring message history, runtime steps, and citations for the current thread.
          </p>
        </div>
      </div>
    );
  }

  let latestAssistantId: string | undefined;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      latestAssistantId = messages[index].id;
      break;
    }
  }

  return (
    <div
      className="flex flex-1 flex-col px-4 pt-6 sm:px-6 lg:px-8"
      role="log"
      aria-label="Conversation messages"
      aria-live="polite"
    >
      <div className="mb-8 border-b border-stroke-subtle pb-6">
        <p className="app-meta text-content-secondary">Conversation</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-content-primary">{title}</h2>
      </div>

      {messages.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-2 py-12 text-center sm:px-8">
          <div className="w-full max-w-2xl">
            <h3 className="text-2xl font-semibold text-content-primary">Start with a concrete task</h3>
            <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-content-secondary">
              Pick a starter or write your own prompt below.
            </p>
            <div className="mt-6 grid gap-2 sm:grid-cols-3">
              {promptStarters.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onPromptSelect(prompt)}
                  className="app-focus-ring rounded-[14px] border border-stroke-subtle bg-surface-strong px-4 py-3 text-left text-sm font-medium leading-5 text-content-primary transition hover:border-stroke-strong hover:bg-surface-emphasis"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-5 pb-8">
          {messages.map((message) => {
            const isUser = message.role === "user";
            const showLiveSteps = !isUser && message.id === latestAssistantId && liveSteps.length > 0;

            return (
              <div key={message.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                <div className="w-full max-w-3xl">
                  <p className={`app-meta mb-3 text-content-secondary ${isUser ? "text-right" : "text-left"}`}>
                    {isUser ? "You" : "Open Model"}
                  </p>

                  {showLiveSteps ? (
                    <div className="mb-3 flex flex-wrap gap-2">
                      {liveSteps.map((step) => (
                        <span
                          key={step.step_id}
                          className={`rounded-full border px-3 py-1 text-xs font-medium ${statusTone(step)}`}
                        >
                          {step.label}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div
                    className={`rounded-[20px] border px-5 py-4 ${
                      isUser
                        ? "border-transparent bg-action text-action-foreground"
                        : "border-stroke-subtle bg-surface-strong text-content-primary"
                    }`}
                  >
                    <p className="whitespace-pre-wrap text-[15px] leading-7">
                      {message.content || (message.pending ? "Generating response..." : "")}
                    </p>
                  </div>

                  {message.error ? (
                    <div className="mt-3 rounded-[16px] border border-error-border bg-error-bg px-4 py-3 text-sm text-error-fg">
                      {message.error}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export const MessageThread = memo(MessageThreadImpl);
