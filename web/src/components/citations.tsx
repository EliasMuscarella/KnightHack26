"use client";

import { createContext, useContext } from "react";

import type { FilingSide, Change } from "@/types/comparison";

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

/** Footnote-style citation: a superscript number; click scrolls to and highlights the cited sentence. */
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
      className="cite ml-0.5 inline-block align-super font-sans text-xs font-medium leading-none text-accent no-underline hover:underline focus-visible:underline"
    >
      {n}
      {withSide ? <span className="sr-only"> ({sideText})</span> : null}
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
  if (ids.length === 0) return <span className="text-sm text-ink-secondary">no citation</span>;
  const unique = [...new Set(ids)];
  return (
    <span className="whitespace-nowrap">
      {unique.map((id, i) => (
        <CitationChip key={id} n={numberOf ? numberOf(id) : start + i} id={id} withSide={withSide} />
      ))}
    </span>
  );
}

/**
 * One numbering for a whole change: AI claims, then rubric answers, then deterministic signals,
 * so a number means the same sentence in every panel of the page.
 */
export function changeCitationNumbering(change: Change): (id: string) => number {
  const interp = change.interpretation;
  const s = change.signals;
  return numberCitations([
    ...(interp.claims ?? []).map((c) => c.cited_sentence_ids),
    ...(interp.rubric ?? []).map((r) => r.cited_sentence_ids ?? []),
    ...[...(s.hypothetical_to_actual ?? []), ...(s.new_entities ?? []), ...(s.new_quantities ?? [])].map((h) => [
      ...(h.old_sentence_ids ?? []),
      ...(h.new_sentence_ids ?? []),
    ]),
  ]);
}

/** Assigns 1-based numbers to sentence ids in first-seen order. */
export function numberCitations(idLists: string[][]): (id: string) => number {
  const numbers = new Map<string, number>();
  for (const list of idLists) {
    for (const id of list) if (!numbers.has(id)) numbers.set(id, numbers.size + 1);
  }
  return (id) => numbers.get(id) ?? 0;
}
