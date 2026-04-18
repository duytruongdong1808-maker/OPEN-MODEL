import type { StepUpdate, UiMessage } from "@/lib/types";

interface MessageThreadProps {
  title: string;
  messages: UiMessage[];
  liveSteps: StepUpdate[];
  isLoading: boolean;
}

function statusTone(step: StepUpdate): string {
  if (step.status === "active") {
    return "border-accent-200 bg-accent-100/70 text-accent-700";
  }
  if (step.status === "complete") {
    return "border-emerald-200 bg-emerald-100 text-emerald-700";
  }
  if (step.status === "error") {
    return "border-rose-200 bg-rose-100 text-rose-700";
  }
  return "border-shell-200 bg-shell-100 text-shell-700";
}

export function MessageThread({
  title,
  messages,
  liveSteps,
  isLoading,
}: MessageThreadProps) {
  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="max-w-md text-center">
          <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-shell-500">Syncing thread</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-shell-900">
            Loading the current conversation
          </h2>
          <p className="mt-3 text-sm leading-6 text-shell-600">
            We are restoring the message history and source state for this thread.
          </p>
        </div>
      </div>
    );
  }

  const latestAssistantId = [...messages].reverse().find((message) => message.role === "assistant")?.id;

  return (
    <div className="flex flex-1 flex-col px-4 pt-6 sm:px-8">
      <div className="mb-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.32em] text-shell-500">Conversation</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-shell-900">{title}</h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-shell-600">
          The center column stays quiet and readable so you can focus on what the assistant is saying while the
          right panel handles live status and citations.
        </p>
      </div>

      {messages.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-[2rem] border border-dashed border-shell-300/80 bg-white/40 px-8 py-16 text-center">
          <div className="max-w-xl">
            <h3 className="text-2xl font-semibold text-shell-900">Start with a real task</h3>
            <p className="mt-3 text-sm leading-6 text-shell-600">
              Ask for a summary, explore a news topic, or use this shell as the first step toward an agent that can
              cite live sources.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {messages.map((message) => {
            const isUser = message.role === "user";
            const showLiveSteps = !isUser && message.id === latestAssistantId && liveSteps.length > 0;

            return (
              <div key={message.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                <div className="w-full max-w-3xl">
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
                    className={`rounded-[1.8rem] px-5 py-4 shadow-sm ${
                      isUser
                        ? "ml-auto bg-shell-900 text-white"
                        : "bg-white/85 text-shell-900 backdrop-blur"
                    }`}
                  >
                    <p className="whitespace-pre-wrap text-[15px] leading-7">
                      {message.content || (message.pending ? "Thinking…" : "")}
                    </p>
                  </div>

                  {message.error ? (
                    <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
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
