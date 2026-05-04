"use client";

import { memo, useEffect, useState } from "react";

import { createBrowserApiClient } from "@/lib/api";
import { formatPublishedAt } from "@/lib/format";
import type {
  AgentStep,
  ChatStreamMode,
  GmailStatus,
  HardwareInfo,
  SourceItem,
  StepUpdate,
} from "@/lib/types";

import {
  IconChevron,
  IconCpu,
  IconLink,
  IconLogOut,
  IconMail,
  IconSliders,
} from "@/components/ui/icons";

interface AgentStatusPanelProps {
  steps: StepUpdate[];
  agentSteps: AgentStep[];
  sources: SourceItem[];
  isStreaming: boolean;
  activeMode: ChatStreamMode | null;
  hasError: boolean;
  gmailStatus: GmailStatus | null;
  gmailActionPending: boolean;
  systemPromptOverride: string;
  open: boolean;
  onSystemPromptOverrideChange: (value: string) => void;
  onGmailLogin: () => void;
  onGmailLogout: () => void;
  onToggle: () => void;
  onClose: () => void;
}

const STATUS_COLOR: Record<StepUpdate["status"], { dot: string; label: string }> = {
  pending: { dot: "bg-text-4", label: "text-text-4" },
  active: { dot: "bg-accent-fg animate-om-pulse", label: "text-text" },
  complete: { dot: "bg-ok-fg", label: "text-text-2" },
  error: { dot: "bg-err-fg", label: "text-err-fg" },
};

function AgentStatusPanelImpl({
  steps,
  agentSteps,
  sources,
  isStreaming,
  activeMode,
  hasError,
  gmailStatus,
  gmailActionPending,
  systemPromptOverride,
  open,
  onSystemPromptOverrideChange,
  onGmailLogin,
  onGmailLogout,
  onToggle,
  onClose,
}: AgentStatusPanelProps) {
  const [tab, setTab] = useState<"runtime" | "sources">("runtime");
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  useEffect(() => {
    let ignore = false;

    createBrowserApiClient()
      .fetchSystemInfo()
      .then((systemInfo) => {
        if (!ignore) {
          setHardware(systemInfo);
        }
      })
      .catch(() => {
        // Runtime details are best-effort; keep the panel usable if detection fails.
      });

    return () => {
      ignore = true;
    };
  }, []);

  if (!open) return null;

  const activeStep = steps.find((step) => step.status === "active");
  const statusLabel = hasError
    ? "Error"
    : isStreaming
      ? activeMode === "agent"
        ? activeStep?.label ?? "Agent reading"
        : activeStep?.label ?? "Generating"
      : steps.length === 0
        ? "Ready"
        : "Trace ready";

  return (
    <>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-20 bg-black/60 backdrop-blur-[2px] xl:hidden"
        onClick={onClose}
      />
      <aside
        id="runtime-panel"
        data-testid="agent-status"
        aria-label="Runtime panel"
        className="om-scroll fixed inset-y-0 right-0 z-30 flex w-[min(380px,92vw)] flex-col overflow-y-auto border-l border-line bg-bg-rail shadow-pop xl:sticky xl:top-0 xl:h-screen xl:w-full xl:shadow-none"
      >
        <header className="border-b border-line px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="om-meta">Runtime</div>
              <h2 className="mt-0.5 text-[13.5px] font-semibold tracking-tight text-text">
                {statusLabel}
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
          </div>
          <div className="mt-3 rounded-xl border border-accent-ring bg-accent-soft px-3 py-2 shadow-[0_0_28px_var(--accent-glow)]">
            <div className="flex items-center gap-2 text-[12px] font-semibold text-accent-fg">
              <span className="h-2 w-2 rounded-full bg-accent-fg shadow-[0_0_12px_var(--accent-fg)]" />
              vLLM local stack
            </div>
            <div className="mt-1 font-mono text-[10.5px] text-text-3">
              Qwen2.5 1.5B + LoRA · 1024 ctx · 256 output
            </div>
          </div>
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
          {hardware?.warning && (
            <div className="mb-2 rounded-md border border-warn-bd bg-warn-bg px-2.5 py-2 text-[11px] leading-relaxed text-warn-fg">
              {hardware.warning}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-text-2">
            <Stat label="Backend" value="vLLM" />
            <Stat label="Context" value="1024 tokens" />
            <Stat label="Max output" value="256 tokens" />
            {hardware ? (
              <>
                <Stat label="Hardware" value={hardware.gpu_name ?? "CPU only"} />
                <Stat label="VRAM" value={hardware.vram_gb != null ? `${hardware.vram_gb} GB` : "—"} />
                <Stat label="Dtype" value={hardware.compute_dtype} />
                <Stat label="Quant" value={hardware.quantization === "4bit" ? "4-bit" : "none"} />
                <Stat label="Model" value={hardware.recommended_model} />
              </>
            ) : (
              <Stat label="Hardware" value="Detecting…" />
            )}
            <Stat label="Mode" value={activeMode === "agent" ? "Mail agent" : "Chat"} />
          </div>
          <button type="button" className="om-btn om-btn-ghost mt-3 w-full justify-center">
            <IconSliders size={13} /> Inference settings
          </button>
          <label className="mt-3 block">
            <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-text-3">
              <IconSliders size={12} /> Custom instructions
            </span>
            <textarea
              value={systemPromptOverride}
              onChange={(event) => onSystemPromptOverrideChange(event.target.value)}
              rows={5}
              placeholder="Tone, constraints, or role for this conversation"
              className="om-scroll min-h-[104px] w-full resize-y rounded-md border border-line bg-bg-input px-2.5 py-2 text-[12.5px] leading-relaxed text-text outline-none transition focus:border-accent-ring"
            />
          </label>
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
      <div className="mt-0.5 break-words text-[12px] text-text">{value}</div>
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
          Send a message to see runtime steps: context, tool calls, and token generation.
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
          <span className="font-mono text-[10.5px] text-text-3">streaming...</span>
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
