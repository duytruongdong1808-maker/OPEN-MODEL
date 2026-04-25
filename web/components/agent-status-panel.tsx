"use client";

import { memo, useEffect, useState } from "react";

import { formatPublishedAt } from "@/lib/format";
import type { AgentStep, GmailStatus, SourceItem, StepUpdate } from "@/lib/types";

import { IconChevron, IconCpu, IconLogOut, IconMail, IconLink, IconSliders } from "./icons";

interface AgentStatusPanelProps {
  steps: StepUpdate[];
  agentSteps: AgentStep[];
  sources: SourceItem[];
  isStreaming: boolean;
  gmailStatus: GmailStatus | null;
  gmailActionPending: boolean;
  open: boolean;
  onGmailLogin: () => void;
  onGmailLogout: () => void;
  onToggle: () => void;
  onClose: () => void;
}

const STATUS_COLOR: Record<StepUpdate["status"], { dot: string; label: string }> = {
  pending:  { dot: "bg-text-4",                     label: "text-text-4" },
  active:   { dot: "bg-accent-fg animate-om-pulse", label: "text-text" },
  complete: { dot: "bg-ok-fg",                      label: "text-text-2" },
  error:    { dot: "bg-err-fg",                     label: "text-err-fg" },
};

function AgentStatusPanelImpl({
  steps,
  agentSteps,
  sources,
  isStreaming,
  gmailStatus,
  gmailActionPending,
  open,
  onGmailLogin,
  onGmailLogout,
  onToggle,
  onClose,
}: AgentStatusPanelProps) {
  const [tab, setTab] = useState<"runtime" | "sources">("runtime");

  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const activeStep = steps.find((step) => step.status === "active");

  return (
    <>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-20 bg-black/60 backdrop-blur-[2px] xl:hidden"
        onClick={onClose}
      />
      <aside
        id="runtime-panel"
        aria-label="Runtime panel"
        className="om-scroll fixed inset-y-0 right-0 z-30 flex w-[min(380px,92vw)] flex-col overflow-y-auto border-l border-line bg-bg-rail shadow-pop xl:sticky xl:top-0 xl:h-screen xl:w-full xl:shadow-none"
      >
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
          <div>
            <div className="om-meta">Runtime</div>
            <h2 className="mt-0.5 text-[13.5px] font-semibold tracking-tight text-text">
              {isStreaming ? activeStep?.label ?? "Working…" : steps.length === 0 ? "Idle" : "Trace ready"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onToggle}
            aria-label="Hide runtime panel"
            className="om-icon-btn om-focus"
          >
            <IconChevron size={16} />
          </button>
        </header>

        <div className="flex border-b border-line px-4 pt-2">
          {(["runtime", "sources"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              className={`relative -mb-px px-3 py-2 text-[12px] font-medium capitalize transition-colors ${
                tab === value ? "text-text" : "text-text-3 hover:text-text-2"
              }`}
            >
              {value}
              {value === "sources" && sources.length > 0 && (
                <span className="ml-1.5 rounded-full bg-bg-emph px-1.5 py-0.5 font-mono text-[10px] text-text-3">
                  {sources.length}
                </span>
              )}
              {tab === value && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded bg-accent-fg" />}
            </button>
          ))}
        </div>

        <div className="flex-1 px-4 py-3">
          {tab === "runtime" ? (
            <RuntimeTrace steps={steps} agentSteps={agentSteps} isStreaming={isStreaming} />
          ) : (
            <SourceTab sources={sources} />
          )}
        </div>

        <div className="border-t border-line px-4 py-3">
          <GmailAccountControl
            status={gmailStatus}
            pending={gmailActionPending}
            onLogin={onGmailLogin}
            onLogout={onGmailLogout}
          />
        </div>

        <div className="border-t border-line px-4 py-3">
          <div className="om-meta mb-2">Inference</div>
          <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-text-2">
            <Stat label="Backend" value="llama.cpp · q4" />
            <Stat label="Context" value="4 096 tok" />
            <Stat label="Memory" value="22.4 GB" />
            <Stat label="Speed" value="38 tok/s" />
          </div>
          <button type="button" className="om-btn om-btn-ghost mt-3 w-full justify-center">
            <IconSliders size={13} /> Inference settings
          </button>
        </div>
      </aside>
    </>
  );
}

function GmailAccountControl({
  status,
  pending,
  onLogin,
  onLogout,
}: {
  status: GmailStatus | null;
  pending: boolean;
  onLogin: () => void;
  onLogout: () => void;
}) {
  const connected = status?.connected ?? false;
  const email = status?.email ?? "Gmail not connected";
  return (
    <div>
      <div className="om-meta mb-2">Gmail</div>
      <div className="flex items-center gap-2.5 rounded-md border border-line bg-bg-raised px-2.5 py-2">
        <span
          className={`grid h-7 w-7 shrink-0 place-items-center rounded-md border ${
            connected
              ? "border-accent-ring bg-accent-soft text-accent-fg"
              : "border-line-strong bg-bg-emph text-text-3"
          }`}
        >
          <IconMail size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12.5px] font-medium text-text">{email}</div>
          <div className="font-mono text-[10px] text-text-3">
            {connected ? "read-only" : "sign in to read mail"}
          </div>
        </div>
        {connected ? (
          <button
            type="button"
            aria-label="Disconnect Gmail"
            disabled={pending}
            onClick={onLogout}
            className="om-icon-btn om-focus"
          >
            <IconLogOut size={14} />
          </button>
        ) : (
          <button
            type="button"
            disabled={pending}
            onClick={onLogin}
            className="om-btn om-btn-ghost shrink-0 px-2.5 py-1.5 text-[11px]"
          >
            Sign in with Google
          </button>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-bg-raised px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wider text-text-4">{label}</div>
      <div className="mt-0.5 text-[12px] text-text">{value}</div>
    </div>
  );
}

function truncateDetail(value: string, max = 220): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 3).trim()}...`;
}

function formatUnknown(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function agentStepDetail(step: AgentStep): string {
  if (step.error) return step.error;
  if (step.kind === "tool") {
    const args = formatUnknown(step.arguments) || "{}";
    const result = formatUnknown(step.result);
    return result ? `args ${args} -> ${result}` : `args ${args}`;
  }
  return step.content ? truncateDetail(step.content) : "";
}

function RuntimeTrace({
  steps,
  agentSteps,
  isStreaming,
}: {
  steps: StepUpdate[];
  agentSteps: AgentStep[];
  isStreaming: boolean;
}) {
  if (steps.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line-strong p-4 text-center">
        <div className="mx-auto mb-2 grid h-8 w-8 place-items-center rounded-full border border-line bg-bg-raised text-text-3">
          <IconCpu size={14} />
        </div>
        <p className="text-[11.5px] leading-relaxed text-text-3">
          Send a message to see runtime steps — retrieval, tool calls, and token generation.
        </p>
      </div>
    );
  }

  return (
    <ol className="relative ml-1.5 border-l border-line pl-4">
      {steps.map((step, i) => {
        const tone = STATUS_COLOR[step.status];
        const detail = agentSteps[i] ? agentStepDetail(agentSteps[i]) : "";
        return (
          <li key={step.step_id} className="relative pb-3 last:pb-0">
            <span
              className={`absolute -left-[22px] top-1.5 h-2 w-2 rounded-full ${tone.dot}`}
              style={step.status === "active" ? { boxShadow: "0 0 0 3px var(--accent-glow)" } : undefined}
            />
            <div className={`text-[12.5px] font-medium ${tone.label}`}>{step.label}</div>
            <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-text-4">
              step {String(i + 1).padStart(2, "0")} · {step.status}
            </div>
            {detail && (
              <div className="mt-1.5 rounded-md border border-line bg-bg-raised px-2 py-1.5 font-mono text-[10.5px] leading-5 text-text-3">
                {truncateDetail(detail)}
              </div>
            )}
          </li>
        );
      })}
      {isStreaming && (
        <li className="relative pl-1 pt-1">
          <span className="font-mono text-[10.5px] text-text-3">↳ streaming…</span>
        </li>
      )}
    </ol>
  );
}

function SourceTab({ sources }: { sources: SourceItem[] }) {
  if (sources.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line-strong p-4 text-center text-[11.5px] leading-relaxed text-text-3">
        Citations from retrieval and tool calls appear here.
      </div>
    );
  }
  return (
    <ul className="flex flex-col gap-1.5" aria-label="Citations">
      {sources.map((source, i) => (
        <li key={source.url}>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="om-focus group flex items-start gap-2.5 rounded-md border border-line bg-bg-raised p-2.5 transition-colors hover:border-line-hi hover:bg-bg-emph"
          >
            <span className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border border-accent-ring bg-accent-soft font-mono text-[10px] font-semibold text-accent-fg">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="line-clamp-2 text-[12.5px] font-medium text-text">{source.title}</div>
              <div className="mt-1 flex items-center gap-1.5 font-mono text-[10px] text-text-3">
                <IconLink size={10} />
                {source.source}
                {source.published_at && (
                  <span className="text-text-4">· {formatPublishedAt(source.published_at)}</span>
                )}
              </div>
            </div>
          </a>
        </li>
      ))}
    </ul>
  );
}

export const AgentStatusPanel = memo(AgentStatusPanelImpl);
