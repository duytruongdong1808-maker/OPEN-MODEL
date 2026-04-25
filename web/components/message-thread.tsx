"use client";

import { memo, useMemo, type ReactNode } from "react";

import type { StepUpdate, UiMessage } from "@/lib/types";

import {
  IconAlert,
  IconCheck,
  IconCompare,
  IconDoc,
  IconModel,
  IconRetry,
  IconSpark,
} from "./icons";

interface MessageThreadProps {
  title: string;
  messages: UiMessage[];
  liveSteps: StepUpdate[];
  isLoading: boolean;
  onPromptSelect: (prompt: string) => void;
}

const STARTERS = [
  { Icon: IconDoc,     title: "Summarize a document", body: "Paste text or a URL — I'll produce a structured brief." },
  { Icon: IconCompare, title: "Compare options",      body: "Side-by-side analysis with pros, cons, and tradeoffs." },
  { Icon: IconSpark,   title: "Plan the next step",   body: "Turn a goal into an actionable, prioritized checklist." },
];

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>,
  );
}

function renderRichText(text: string) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let buffer: ReactNode[] = [];
  const flushP = () => {
    if (buffer.length === 0) return;
    out.push(<p key={`p${out.length}`}>{buffer}</p>);
    buffer = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith("- ")) {
      flushP();
      const items: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("- ")) {
        items.push(lines[i].trim().slice(2));
        i += 1;
      }
      i -= 1;
      out.push(
        <ul key={`u${out.length}`} className="my-2 list-disc pl-5">
          {items.map((item, k) => (
            <li key={k}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
    } else if (line.trim() === "") {
      flushP();
    } else if (/^\*\*[^*]+\*\*$/.test(line.trim())) {
      flushP();
      out.push(
        <h4 key={`h${out.length}`} className="mt-5 mb-1.5 text-[14px] font-semibold tracking-tight text-text">
          {line.trim().replace(/\*\*/g, "")}
        </h4>,
      );
    } else {
      if (buffer.length > 0) buffer.push(<br key={`br${i}`} />);
      buffer.push(renderInline(line));
    }
  }
  flushP();
  return out;
}

function PromptStarters({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="relative mx-auto max-w-[720px] px-7 pt-20 pb-14 text-center">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-[-100px] -top-10 h-[380px]"
        style={{ background: "radial-gradient(circle at center, var(--accent-glow), transparent 60%)" }}
      />
      <div className="relative mx-auto mb-4 grid h-11 w-11 place-items-center rounded-xl border border-accent-ring bg-accent-soft text-accent-fg">
        <IconSpark size={20} />
      </div>
      <h2 className="relative mb-2 text-[26px] font-semibold tracking-tight text-text">What should we work on?</h2>
      <p className="relative mx-auto max-w-[440px] text-[14px] leading-6 text-text-3">
        Open Model runs entirely on your hardware. Pick a starter, or write your own prompt below.
      </p>
      <div className="relative mt-7 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {STARTERS.map(({ Icon, title, body }) => (
          <button
            key={title}
            type="button"
            onClick={() => onPick(title)}
            className="om-focus group flex flex-col gap-1.5 rounded-lg border border-line bg-bg-raised p-3.5 text-left transition-all hover:-translate-y-px hover:border-line-hi hover:bg-bg-emph"
          >
            <div className="mb-1 grid h-7 w-7 place-items-center rounded-md border border-line bg-white/[0.04] text-text-2">
              <Icon size={16} />
            </div>
            <div className="text-[13px] font-semibold text-text">{title}</div>
            <div className="text-xs leading-5 text-text-3">{body}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function UserMessage({ message }: { message: UiMessage }) {
  return (
    <div className="flex flex-row-reverse gap-3.5">
      <div className="flex max-w-[85%] flex-col items-end">
        <div className="mb-1.5 text-[12px] font-semibold text-text-2">You</div>
        <div className="inline-block max-w-full rounded-[14px_14px_4px_14px] border border-line-strong bg-bg-raised px-3.5 py-2.5 text-left text-[14.5px] leading-relaxed">
          {message.content}
        </div>
      </div>
    </div>
  );
}

function AssistantMessage({ message, streaming }: { message: UiMessage; streaming: boolean }) {
  return (
    <div className="group flex gap-3.5">
      <div className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-accent-ring bg-accent-soft text-accent-fg">
        <IconModel size={14} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-center gap-2.5">
          <span className="text-[12px] font-semibold text-text-2">Open Model</span>
          {streaming && (
            <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] text-accent-fg">
              <span className="h-1 w-1 animate-om-pulse rounded-full bg-current" />
              <span className="h-1 w-1 animate-om-pulse rounded-full bg-current [animation-delay:.15s]" />
              <span className="h-1 w-1 animate-om-pulse rounded-full bg-current [animation-delay:.3s]" />
              Generating
            </span>
          )}
        </div>
        <div className="text-[15px] leading-[1.7] text-text [&>p]:mb-3.5 [&>p:last-child]:mb-0">
          {renderRichText(message.content)}
          {streaming && (
            <span className="ml-0.5 inline-block h-4 w-2 -translate-y-[3px] animate-om-blink bg-accent-fg align-baseline" />
          )}
        </div>

        {message.sources.length > 0 && (
          <div className="mt-3.5 flex flex-wrap gap-1.5">
            {message.sources.map((source, i) => (
              <a
                key={source.url}
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="om-focus inline-flex max-w-[280px] items-center gap-1.5 rounded-full border border-line bg-bg-raised py-1 pl-1 pr-2.5 text-[11.5px] text-text-2 transition-colors hover:border-line-hi hover:text-text"
              >
                <span className="grid h-[18px] w-[18px] place-items-center rounded-full border border-line-strong bg-white/[0.04] font-mono text-[10px] font-semibold text-accent-fg">
                  {i + 1}
                </span>
                <span className="truncate font-medium">{source.title}</span>
                <span className="font-mono text-[10px] text-text-4">{source.source}</span>
              </a>
            ))}
          </div>
        )}

        {!streaming && message.content && !message.error && (
          <div className="mt-2.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-text-3 hover:bg-bg-raised hover:text-text">
              <IconCheck size={13} /> Copy
            </button>
            <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-text-3 hover:bg-bg-raised hover:text-text">
              <IconRetry size={13} /> Regenerate
            </button>
          </div>
        )}

        {message.error && (
          <div className="mt-3 flex items-start gap-3 rounded-lg border border-err-bd bg-err-bg px-3.5 py-3 text-err-fg">
            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-red-400/10">
              <IconAlert size={16} />
            </div>
            <div className="flex-1">
              <div className="text-[13px] font-semibold text-text">Generation failed</div>
              <div className="text-[12.5px] leading-relaxed text-text-2">{message.error}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MessageThreadImpl({
  title,
  messages,
  liveSteps,
  isLoading,
  onPromptSelect,
}: MessageThreadProps) {
  const latestAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return undefined;
  }, [messages]);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="max-w-md text-center">
          <p className="om-meta">Syncing thread</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text">Loading conversation</h2>
          <p className="mt-3 text-sm leading-6 text-text-3">Restoring messages, runtime steps, and citations.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col" role="log" aria-label="Conversation messages" aria-live="polite">
      <header className="flex items-center justify-between gap-3 border-b border-line px-6 py-3.5">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-4">Workspace · Local</div>
          <h1 className="mt-1 text-[16px] font-semibold tracking-tight text-text">{title}</h1>
        </div>
        <span className="om-chip">
          <span className="font-mono text-[11px]">Llama-3.1-70B</span>
        </span>
      </header>

      {messages.length === 0 ? (
        <PromptStarters onPick={onPromptSelect} />
      ) : (
        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-5 px-7 py-8">
          {messages.map((message) => {
            const showLiveSteps =
              message.role === "assistant" && message.id === latestAssistantId && liveSteps.length > 0;
            return (
              <div key={message.id}>
                {showLiveSteps && (
                  <div className="mb-3 flex flex-wrap gap-1.5 pl-[42px]">
                    {liveSteps.map((step) => (
                      <span
                        key={step.step_id}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${
                          step.status === "active"
                            ? "border-accent-ring bg-accent-soft text-accent-fg"
                            : step.status === "complete"
                            ? "border-ok-bd bg-ok-bg text-ok-fg"
                            : step.status === "error"
                            ? "border-err-bd bg-err-bg text-err-fg"
                            : "border-line-strong bg-white/[0.04] text-text-3"
                        }`}
                      >
                        {step.label}
                      </span>
                    ))}
                  </div>
                )}
                {message.role === "user" ? (
                  <UserMessage message={message} />
                ) : (
                  <AssistantMessage
                    message={message}
                    streaming={Boolean(message.pending) && !message.error}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export const MessageThread = memo(MessageThreadImpl);
