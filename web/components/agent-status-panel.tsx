import { memo } from "react";

import { SourceList } from "@/components/source-list";
import type { SourceItem, StepUpdate } from "@/lib/types";

const statusTone: Record<StepUpdate["status"], string> = {
  pending: "border-stroke-subtle bg-action-muted text-content-secondary",
  active: "border-interactive-border bg-interactive-active text-content-tertiary",
  complete: "border-success-border bg-success-bg text-success-fg",
  error: "border-error-border bg-error-bg text-error-fg",
};

interface AgentStatusPanelProps {
  open: boolean;
  onClose: () => void;
  steps: StepUpdate[];
  sources: SourceItem[];
}

function AgentStatusPanelImpl({
  open,
  onClose,
  steps,
  sources,
}: AgentStatusPanelProps) {
  const panelClasses = open
    ? "pointer-events-auto translate-x-0 opacity-100"
    : "pointer-events-none translate-x-6 opacity-0 xl:pointer-events-auto xl:translate-x-0 xl:opacity-100";

  return (
    <>
      <div
        aria-hidden={!open}
        className={`fixed inset-0 z-20 bg-overlay transition xl:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />

      <aside
        id="runtime-panel"
        aria-label="Runtime status"
        className={`app-shell-scrollbar app-surface fixed inset-y-3 right-3 z-30 flex w-[min(22rem,calc(100vw-1.5rem))] flex-col overflow-y-auto rounded-[24px] p-5 transition xl:sticky xl:top-3 xl:h-[calc(100vh-1.5rem)] xl:w-full xl:translate-x-0 xl:opacity-100 ${panelClasses}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="app-meta text-content-secondary">Runtime</p>
            <h2 className="mt-3 text-xl font-semibold text-content-primary">Runtime panel</h2>
            <p className="mt-2 text-sm leading-6 text-content-secondary">
              Watch step status and citations without pushing the response out of focus.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="app-button app-button-secondary app-focus-ring px-3 py-2 text-xs font-medium xl:hidden"
          >
            Close
          </button>
        </div>

        <section className="mt-8 border-t border-stroke-subtle pt-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-content-primary">Current steps</h3>
            <span className="app-meta text-content-secondary">{steps.length || 0} live</span>
          </div>

          <div className="space-y-3" role="status" aria-live="polite">
            {steps.length === 0 ? (
              <div className="rounded-[16px] border border-dashed border-stroke-strong bg-interactive-hover px-5 py-6 text-sm leading-6 text-content-secondary">
                Runtime status will appear here when the assistant starts working.
              </div>
            ) : (
              steps.map((step) => (
                <div
                  key={step.step_id}
                  className={`rounded-[16px] border px-4 py-4 ${statusTone[step.status]}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium">{step.label}</p>
                    <span
                      className="text-[11px] font-medium uppercase tracking-[0.18em]"
                      aria-label={`Step status: ${step.status}`}
                    >
                      {step.status}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="mt-8 border-t border-stroke-subtle pt-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-content-primary">Sources</h3>
            <span className="app-meta text-content-secondary">{sources.length || 0} items</span>
          </div>
          <SourceList sources={sources} />
        </section>
      </aside>
    </>
  );
}

export const AgentStatusPanel = memo(AgentStatusPanelImpl);
