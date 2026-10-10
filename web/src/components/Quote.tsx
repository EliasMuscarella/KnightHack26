"use client";

import { useId, useState } from "react";

import { QUOTE_MAX_CHARS, trimQuote } from "@/lib/quote";

/**
 * A verbatim filing sentence. Long sentences show an exact prefix with a visible ellipsis
 * and a "Show full sentence" toggle; the text itself is never altered.
 */
export function Quote({ text, max = QUOTE_MAX_CHARS, className = "" }: { text: string; max?: number; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const { head, trimmed } = trimQuote(text, max);
  return (
    <blockquote className={`filing-text quote ${className}`}>
      <p id={id}>
        <span aria-hidden="true" className="quote-mark">
          “
        </span>
        {open || !trimmed ? text : head}
        {trimmed && !open ? (
          <span className="font-sans font-semibold text-ink-faint" aria-label="(sentence continues)">
            {" "}…
          </span>
        ) : null}
        <span aria-hidden="true" className="quote-mark">
          ”
        </span>
      </p>
      {trimmed ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className="mt-1 font-sans text-sm font-semibold text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
        >
          {open ? "Show less" : "Show full sentence"}
        </button>
      ) : null}
    </blockquote>
  );
}
