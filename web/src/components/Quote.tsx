"use client";

import { useId, useMemo, useState } from "react";

import type { DiffSpan } from "@/types/comparison";

import { MarkedText, type MarkStatus } from "@/components/MarkedText";
import { QUOTE_MAX_CHARS } from "@/lib/quote";
import { markedRanges, snippetWindow } from "@/lib/snippet";

export interface QuoteProps {
  text: string;
  /** "old" = last year (muted, strikes), "new" = this year (ink, highlighter). */
  side: "old" | "new";
  status?: MarkStatus;
  /** The spans to draw (may have case-only edits neutralized for display). */
  spans?: DiffSpan[] | null;
  /** The sentence's stored `diff_spans`, used to place the window; defaults to `spans`. */
  sourceSpans?: DiffSpan[] | null;
  max?: number;
  className?: string;
}

/**
 * A verbatim filing sentence in the serif, with the analyst's marks. A long sentence shows an
 * exact window around this side's marked words (lib/snippet.ts), a visible ellipsis on every
 * trimmed side and a "Show full sentence" control; the text itself is never altered.
 */
export function Quote({ text, side, status = "unchanged", spans, sourceSpans, max = QUOTE_MAX_CHARS, className = "" }: QuoteProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const evidenceSpans = sourceSpans === undefined ? spans : sourceSpans;
  const win = useMemo(() => {
    const evidence = markedRanges({ text, status, diff_spans: evidenceSpans }, side === "new" ? "insert" : "delete");
    return snippetWindow(text, evidence, max);
  }, [text, status, evidenceSpans, side, max]);
  const trimmed = win.start > 0 || win.end < text.length;
  return (
    <blockquote className={`quote ${side === "old" ? "is-old" : "is-new"} ${className}`}>
      <p id={id}>
        {trimmed && !open ? (
          <MarkedText text={text} spans={spans} side={side} status={status} start={win.start} end={win.end} />
        ) : (
          <MarkedText text={text} spans={spans} side={side} status={status} />
        )}
      </p>
      {trimmed ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className="mt-1 font-sans text-sm font-medium text-accent underline underline-offset-2"
        >
          {open ? "Show less" : "Show full sentence"}
        </button>
      ) : null}
    </blockquote>
  );
}
