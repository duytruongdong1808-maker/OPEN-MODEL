import { formatPublishedAt } from "@/lib/format";
import type { SourceItem } from "@/lib/types";

export function SourceList({ sources }: { sources: SourceItem[] }) {
  if (sources.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-shell-300/80 bg-white/50 px-5 py-6 text-sm text-shell-600">
        Sources will appear here as the news agent starts attaching citations.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {sources.map((source, index) => (
        <a
          key={`${source.url}-${index}`}
          href={source.url}
          target="_blank"
          rel="noreferrer"
          className="block rounded-3xl border border-black/5 bg-white/80 p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
        >
          <p className="font-medium text-shell-900">{source.title}</p>
          <div className="mt-3 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.22em] text-shell-500">
            <span>{source.source}</span>
            <span>{formatPublishedAt(source.published_at)}</span>
          </div>
        </a>
      ))}
    </div>
  );
}
