"use client";

import type { ReactElement } from "react";

type Variant = "compact" | "full";

interface Props {
  group: string;
  text: string;
  variant?: Variant;
}

type Section = {
  title: string;
  lines: string[];
};

function cleanMarkdown(value: string) {
  return value
    .replace(/^#{1,4}\s*/, "")
    .replace(/\*\*/g, "")
    .replace(/^>\s*/, "")
    .trim();
}

function parseSections(text: string): Section[] {
  const sections: Section[] = [];
  let current: Section = { title: "Panorama general", lines: [] };

  for (const raw of text.replace(/\r/g, "").split("\n")) {
    const line = raw.trimEnd();
    if (/^#{1,4}\s+/.test(line)) {
      if (current.lines.some((item) => item.trim())) sections.push(current);
      current = { title: cleanMarkdown(line), lines: [] };
      continue;
    }
    if (line.trim() === "---") continue;
    current.lines.push(line);
  }

  if (current.lines.some((item) => item.trim())) sections.push(current);
  return sections;
}

function firstParagraph(lines: string[]) {
  return lines
    .join("\n")
    .split(/\n{2,}/)
    .map((item) => cleanMarkdown(item))
    .find((item) => item && !item.startsWith("|") && !item.startsWith("- "))
    ?? "";
}

function findSection(sections: Section[], pattern: RegExp) {
  return sections.find((section) => pattern.test(section.title));
}

function InlineText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={index}>{part.slice(2, -2)}</strong>;
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

function TableBlock({ rows }: { rows: string[] }) {
  const parsed = rows
    .filter((row) => !/^\|\s*-/.test(row))
    .map((row) => row.split("|").slice(1, -1).map((cell) => cleanMarkdown(cell)));
  const [head, ...body] = parsed;
  if (!head || body.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-md border border-[var(--border-subtle)] my-3">
      <table className="min-w-full text-xs">
        <thead>
          <tr style={{ background: "rgba(255,255,255,0.04)" }}>
            {head.map((cell, index) => (
              <th key={index} className="px-2.5 py-2 text-left whitespace-nowrap">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-[var(--border-subtle)]">
              {row.map((cell, index) => (
                <td key={index} className="px-2.5 py-2 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectionContent({ lines }: { lines: string[] }) {
  const nodes: ReactElement[] = [];
  let table: string[] = [];
  let list: string[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) {
      nodes.push(
        <p key={`p-${nodes.length}`} className="text-sm leading-7" style={{ color: "var(--text)" }}>
          <InlineText text={text} />
        </p>
      );
    }
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    nodes.push(
      <ul key={`ul-${nodes.length}`} className="space-y-2">
        {list.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm leading-6" style={{ color: "var(--text)" }}>
            <span className="mt-2 h-1.5 w-1.5 rounded-full shrink-0" style={{ background: "var(--wc-gold)" }} />
            <span><InlineText text={cleanMarkdown(item.replace(/^-\s*/, ""))} /></span>
          </li>
        ))}
      </ul>
    );
    list = [];
  };
  const flushTable = () => {
    if (!table.length) return;
    const node = <TableBlock key={`table-${nodes.length}`} rows={table} />;
    if (node) nodes.push(node);
    table = [];
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      flushList();
      flushTable();
      continue;
    }
    if (line.startsWith("|")) {
      flushParagraph();
      flushList();
      table.push(line);
      continue;
    }
    if (line.startsWith("- ")) {
      flushParagraph();
      flushTable();
      list.push(line);
      continue;
    }
    flushList();
    flushTable();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  flushTable();
  return <div className="space-y-3">{nodes}</div>;
}

export default function GroupNarrativeCard({ group, text, variant = "full" }: Props) {
  const sections = parseSections(text);
  const panorama = sections[0];
  const summary = firstParagraph(panorama?.lines ?? []);
  const keyMatch = firstParagraph(findSection(sections, /partido clave/i)?.lines ?? []);
  const finalPhrase = firstParagraph(findSection(sections, /frase/i)?.lines ?? []);

  if (variant === "compact") {
    return (
      <details className="stat-card !p-0 text-left group" style={{ overflow: "hidden" }}>
        <summary
          className="cursor-pointer list-none flex items-center justify-between gap-3 px-4 py-3"
        >
          <p
            className="text-[10px] uppercase tracking-[0.18em]"
            style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}
          >
            Grupo {group}
          </p>
          <span className="flex items-center gap-2 text-[10px]" style={{ color: "var(--text-muted)" }}>
            <span className="px-2 py-1 rounded-sm bg-white/5">Previa IA</span>
            <span>Desplegar</span>
            <span className="inline-block transition-transform group-open:rotate-180">▾</span>
          </span>
        </summary>

        <div className="px-4 pb-4">
          <p className="text-sm leading-7 mb-3" style={{ color: "var(--text)" }}>
            {summary}
          </p>
          {keyMatch && (
            <div className="rounded-md border border-[var(--border-subtle)] p-3 mb-3 bg-white/[0.025]">
              <p className="text-[10px] uppercase tracking-[0.14em] mb-1" style={{ color: "var(--text-muted)" }}>
                Partido clave
              </p>
              <p className="text-xs leading-6" style={{ color: "var(--text)" }}>{keyMatch}</p>
            </div>
          )}
          {finalPhrase && (
            <p className="text-xs leading-6 italic" style={{ color: "var(--text-muted)" }}>
              {finalPhrase}
            </p>
          )}
        </div>
      </details>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-[var(--border-subtle)] p-4 bg-white/[0.025]">
        <p
          className="text-[10px] uppercase tracking-[0.18em] mb-2"
          style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}
        >
          GroupNarrative-Preview
        </p>
        <h3 className="text-lg font-black mb-2" style={{ color: "var(--text)" }}>
          Grupo {group}: previa de jornada
        </h3>
        <p className="text-sm leading-7" style={{ color: "var(--text-muted)" }}>
          {summary}
        </p>
      </div>

      {sections.slice(1).map((section) => (
        <section key={section.title} className="rounded-md border border-[var(--border-subtle)] p-4 bg-black/[0.08]">
          <h4
            className="text-[11px] uppercase tracking-[0.16em] mb-3"
            style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}
          >
            {section.title}
          </h4>
          <SectionContent lines={section.lines} />
        </section>
      ))}
    </div>
  );
}
