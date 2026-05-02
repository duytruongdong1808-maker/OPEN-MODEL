"use client";

import type { ReactNode } from "react";

const SECTION_TITLES = [
  "Tóm tắt",
  "Ý chính",
  "Việc cần làm",
  "Mốc thời gian / deadline",
  "Người / bên liên quan",
  "File đính kèm",
] as const;

type SectionTitle = (typeof SECTION_TITLES)[number];
type ParsedSections = Record<SectionTitle, string[]>;

function normalizeHeading(line: string) {
  return line
    .trim()
    .replace(/^\*\*/, "")
    .replace(/\*\*:?\s*$/, "")
    .trim();
}

function parseSections(content: string): ParsedSections | null {
  const sections = SECTION_TITLES.reduce(
    (accumulator, title) => ({ ...accumulator, [title]: [] }),
    {} as ParsedSections,
  );
  let current: SectionTitle | null = null;

  for (const line of content.split("\n")) {
    const heading = normalizeHeading(line);
    if ((SECTION_TITLES as readonly string[]).includes(heading)) {
      current = heading as SectionTitle;
      continue;
    }
    if (current) sections[current].push(line);
  }

  const hasAllSections = SECTION_TITLES.every((title) => sections[title].some((line) => line.trim()));
  return hasAllSections ? sections : null;
}

function cleanItem(line: string) {
  return line.trim().replace(/^[-*]\s+/, "").trim();
}

function sectionText(lines: string[]) {
  return lines.map(cleanItem).filter(Boolean).join(" ");
}

function sectionItems(lines: string[]) {
  return lines.map(cleanItem).filter(Boolean);
}

function inferPriority(content: string, actions: string[], deadlines: string[]) {
  const normalized = content.toLowerCase();
  if (/(urgent|asap|khẩn|gấp|hôm nay|today|incident|outage)/i.test(normalized)) {
    return { label: "Cao", className: "border-red-400/35 bg-red-400/10 text-red-200" };
  }
  if (
    actions.some((item) => !/không thấy/i.test(item)) ||
    deadlines.some((item) => !/không thấy/i.test(item))
  ) {
    return { label: "Trung bình", className: "border-amber-300/35 bg-amber-300/10 text-amber-100" };
  }
  return { label: "Thấp", className: "border-emerald-300/35 bg-emerald-300/10 text-emerald-100" };
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

function renderPlainMarkdown(text: string) {
  const out: ReactNode[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) continue;
    if (line.trim().startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("- ")) {
        items.push(lines[i].trim().slice(2));
        i += 1;
      }
      i -= 1;
      out.push(
        <ul key={`u${out.length}`} className="my-2 list-disc pl-5">
          {items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\*\*[^*]+\*\*$/.test(line.trim())) {
      out.push(
        <h4 key={`h${out.length}`} className="mt-5 mb-1.5 text-[14px] font-semibold text-text">
          {line.trim().replace(/\*\*/g, "")}
        </h4>,
      );
      continue;
    }
    out.push(<p key={`p${out.length}`}>{renderInline(line)}</p>);
  }
  return out;
}

export function EmailSummaryCard({ content }: { content: string }) {
  const sections = parseSections(content);
  if (!sections) return <>{renderPlainMarkdown(content)}</>;

  const actions = sectionItems(sections["Việc cần làm"]);
  const deadlines = sectionItems(sections["Mốc thời gian / deadline"]);
  const attachments = sectionItems(sections["File đính kèm"]);
  const priority = inferPriority(content, actions, deadlines);

  return (
    <article className="max-w-[760px] rounded-lg border border-line bg-bg-raised/70 p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${priority.className}`}>
          Ưu tiên {priority.label}
        </span>
        {deadlines.some((item) => !/không thấy/i.test(item)) ? (
          <span className="rounded-full border border-sky-300/35 bg-sky-300/10 px-2 py-0.5 text-[11px] font-semibold text-sky-100">
            Có deadline
          </span>
        ) : null}
      </div>

      <section>
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-text-3">Tóm tắt</h4>
        <p className="mt-1 text-[14.5px] leading-6 text-text">{sectionText(sections["Tóm tắt"])}</p>
      </section>

      <section className="mt-4">
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-text-3">Ý chính</h4>
        <ul className="mt-2 space-y-1.5">
          {sectionItems(sections["Ý chính"]).map((item, index) => (
            <li key={index} className="text-[13.5px] leading-5 text-text-2">
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-4">
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-text-3">Việc cần làm</h4>
        <ul className="mt-2 space-y-2">
          {actions.map((item, index) => (
            <li key={index} className="flex gap-2 text-[13.5px] leading-5 text-text">
              <span className="mt-1.5 h-3 w-3 shrink-0 rounded border border-line-strong bg-bg" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <section>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-text-3">
            Mốc thời gian / deadline
          </h4>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {deadlines.map((item, index) => (
              <span key={index} className="rounded-full border border-line bg-bg px-2 py-1 text-[12px] text-text-2">
                {item}
              </span>
            ))}
          </div>
        </section>

        <section>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-text-3">
            File đính kèm
          </h4>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {attachments.map((item, index) => (
              <span key={index} className="rounded-md border border-line bg-bg px-2 py-1 text-[12px] text-text-2">
                {item}
              </span>
            ))}
          </div>
        </section>
      </div>

      <section className="mt-4">
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-text-3">
          Người / bên liên quan
        </h4>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {sectionItems(sections["Người / bên liên quan"]).map((item, index) => (
            <span key={index} className="rounded-md border border-line bg-bg px-2 py-1 text-[12px] text-text-2">
              {item}
            </span>
          ))}
        </div>
      </section>
    </article>
  );
}
