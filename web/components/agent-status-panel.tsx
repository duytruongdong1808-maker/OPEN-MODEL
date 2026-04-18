import type { SourceItem, StepUpdate } from "@/lib/types";
import { SourceList } from "@/components/source-list";

const statusTone: Record<StepUpdate["status"], string> = {
  pending: "bg-shell-200 text-shell-700",
  active: "bg-accent-100 text-accent-700",
  complete: "bg-emerald-100 text-emerald-700",
  error: "bg-rose-100 text-rose-700",
};

interface AgentStatusPanelProps {
  open: boolean;
  onClose: () => void;
  steps: StepUpdate[];
  sources: SourceItem[];
}

export function AgentStatusPanel({
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
        className={`fixed inset-0 z-20 bg-shell-900/20 backdrop-blur-sm transition xl:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />
      <aside
        className={`app-shell-scrollbar fixed inset-y-4 right-4 z-30 flex w-[min(22rem,calc(100vw-2rem))] flex-col overflow-y-auto rounded-[2rem] border border-black/5 bg-[var(--panel-bg)] p-5 shadow-shell backdrop-blur xl:static xl:inset-auto xl:w-[22rem] xl:translate-x-0 xl:opacity-100 ${panelClasses}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.34em] text-shell-500">Agent status</p>
            <h2 className="mt-2 text-xl font-semibold text-shell-900">Live reasoning surface</h2>
            <p className="mt-2 text-sm leading-6 text-shell-600">
              Step summaries and source cards stay compact so the answer remains the main event.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/5 px-3 py-2 text-xs font-medium text-shell-600 transition hover:border-shell-300 hover:text-shell-900 xl:hidden"
          >
            Close
          </button>
        </div>

        <section className="mt-8">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-shell-900">Current steps</h3>
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-shell-500">
              {steps.length || 0} live
            </span>
          </div>

          <div className="space-y-3">
            {steps.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-shell-300/80 bg-white/40 px-5 py-6 text-sm text-shell-600">
                The panel is standing by. As soon as the assistant starts working, each major step will appear here.
              </div>
            ) : (
              steps.map((step) => (
                <div
                  key={step.step_id}
                  className="rounded-3xl border border-black/5 bg-white/75 px-4 py-4 shadow-sm"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium text-shell-900">{step.label}</p>
                    <span
                      className={`rounded-full px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ${statusTone[step.status]}`}
                    >
                      {step.status}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="mt-8">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-shell-900">Sources</h3>
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-shell-500">
              {sources.length || 0} items
            </span>
          </div>
          <SourceList sources={sources} />
        </section>
      </aside>
    </>
  );
}
