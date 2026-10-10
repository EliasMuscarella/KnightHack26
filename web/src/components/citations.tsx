"use client";

import { createContext, useContext } from "react";

import type { FilingSide } from "@/types/comparison";

export interface SentenceRef {
  id: string;
  side: FilingSide;
  text: string;
  is_heading: boolean;
}

export interface FilingRef {
  fiscal_year: number;
  form: string;
  edgar_url: string;
  filing_date: string;
}

export interface CitationApi {
  index: Record<string, SentenceRef>;
  filings: { old: FilingRef; new: FilingRef };
  isFixture: boolean;
  jumpTo: (sentenceId: string, source?: HTMLElement | null) => void;
}

export const CitationContext = createContext<CitationApi | null>(null);

export function useCitations(): CitationApi {
  const ctx = useContext(CitationContext);
  if (!ctx) throw new Error("useCitations must be used inside CitationContext");
  return ctx;
}

function preview(text: string, max = 140): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Numbered citation chip `[n]`; click scrolls to and highlights the cited sentence. */
export function CitationChip({ n, id, withSide = false }: { n: number; id: string; withSide?: boolean }) {
  const { index, filings, jumpTo } = useCitations();
  const ref = index[id];
  const sideText = ref ? `FY${ref.side === "old" ? filings.old.fiscal_year : filings.new.fiscal_year}` : "unknown filing";
  return (
    <a
      href={`#s-${id}`}
      data-cite-id={id}
      onClick={(e) => {
        e.preventDefault();
        jumpTo(id, e.currentTarget);
      }}
      title={ref ? `${sideText}: ${preview(ref.text)}` : id}
      aria-label={`Citation ${n}, ${sideText} sentence${ref ? `: ${preview(ref.text, 80)}` : ""}. Jump to sentence.`}
      className="inline-flex items-center rounded border border-line-strong bg-surface px-1.5 py-px font-mono text-xs font-semibold text-accent no-underline shadow-sm hover:border-accent hover:bg-accent-bg"
    >
      [{n}
      {withSide ? <span className="ml-1 font-sans font-medium text-ink-faint">{sideText}</span> : null}]
    </a>
  );
}

/**
 * Chips for a list of cited sentence ids. By default they are numbered from `start`; pass
 * `numberOf` to number by unique sentence id across a whole panel, so one sentence always
 * has the same number and two different sentences never share one.
 */
export function CitationChips({
  ids,
  withSide = false,
  start = 1,
  numberOf,
}: {
  ids: string[];
  withSide?: boolean;
  start?: number;
  numberOf?: (id: string) => number;
}) {
  if (ids.length === 0) return <span className="text-xs text-ink-faint">no citation</span>;
  const unique = [...new Set(ids)];
  return (
    <span className="inline-flex flex-wrap gap-1">
      {unique.map((id, i) => (
        <CitationChip key={id} n={numberOf ? numberOf(id) : start + i} id={id} withSide={withSide} />
      ))}
    </span>
  );
}

/** Assigns 1-based numbers to sentence ids in first-seen order. */
export function numberCitations(idLists: string[][]): (id: string) => number {
  const numbers = new Map<string, number>();
  for (const list of idLists) {
    for (const id of list) if (!numbers.has(id)) numbers.set(id, numbers.size + 1);
  }
  return (id) => numbers.get(id) ?? 0;
}
