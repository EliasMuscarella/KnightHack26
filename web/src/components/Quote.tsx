"use client";

import { useId, useState } from "react";

import type { DiffSpan } from "@/types/comparison";

import { MarkedText, type MarkStatus } from "@/components/MarkedText";
import { lastMarkedOffset } from "@/lib/diffDisplay";
import { QUOTE_MAX_CHARS, trimQuote } from "@/lib/quote";

/** A trimmed quote may grow up to this many characters so that its marked words stay visible. */
export const QUOTE_MARKS_VISIBLE_MAX = 600;

export interface QuoteProps {
  text: string;
  /** "old" = last year (muted, strikes), "new" = this year (ink, highlighter). */
  side: "old" | "new";
  status?: MarkStatus;
  spans?: DiffSpan[] | null;
  max?: number;
  className?: string;
}

/**
 * A verbatim filing sentence in the serif, with the analyst's marks. Long sentences show an
 * exact prefix with a visible ellipsis and a "Show full sentence" control; the text itself is
 * never altered.
 */
export function Quote({ text, side, status = "unchanged", spans, max = QUOTE_MAX_CHARS, className = "" }: QuoteProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  // Never trim away the words the diff marked: extend the window to the last marked span.
  const marked = status === "modified" ? lastMarkedOffset(spans) : 0;
  const budget = marked > max ? Math.min(QUOTE_MARKS_VISIBLE_MAX, marked + 40) : max;
  const { head, trimmed } = trimQuote(text, budget);
  const limit = open || !trimmed ? undefined : head.length;
  return (
    <blockquote className={`quote ${side === "old" ? "is-old" : "is-new"} ${className}`}>
      <p id={id}>
        <MarkedText text={text} spans={spans} side={side} status={status} limit={limit} />
        {trimmed && !open ? (
          <span className="font-sans text-ink-secondary" aria-label="(sentence continues)">
            {" "}
            …
          </span>
        ) : null}
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
