import { memo } from "react";

import { formatPublishedAt } from "@/lib/format";
import type { SourceItem } from "@/lib/types";

function SourceListImpl({ sources }: { sources: SourceItem[] }) {
  if (sources.length === 0) {
    return (
      <div className="rounded-[16px] border border-dashed border-stroke-strong bg-interactive-hover px-5 py-6 text-sm leading-6 text-content-secondary">
        Sources will appear here when the assistant attaches citations.
      </div>
    );
  }

  return (
    <ul className="space-y-3" aria-label="Citations">
      {sources.map((source) => (
        <li key={source.url}>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="app-focus-ring block rounded-[16px] border border-stroke-subtle bg-surface-strong p-4 transition hover:border-stroke-strong hover:bg-surface-emphasis"
          >
            <p className="font-medium text-content-primary">{source.title}</p>
            <div className="mt-3 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.22em] text-content-secondary">
              <span>{source.source}</span>
              <span>{formatPublishedAt(source.published_at)}</span>
            </div>
          </a>
        </li>
      ))}
    </ul>
  );
}

export const SourceList = memo(SourceListImpl);
