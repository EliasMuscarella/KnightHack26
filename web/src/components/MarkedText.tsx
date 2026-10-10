/**
 * A verbatim filing sentence drawn the way an analyst marks up a printed 10-K (DESIGN.md):
 * this year's added or changed words carry the highlighter; last year's removed words are
 * struck through. Only spans the deterministic diff produced are ever marked, and a changed
 * span without letters or digits (punctuation or spacing only) is drawn as plain text. Text is
 * rendered as text; nothing is injected as HTML. Server-safe (no hooks).
 */
import type { DiffSpan } from "@/types/comparison";

import { hasWordChars, mergeChangedSpans, sliceSpans } from "@/lib/diffDisplay";

export type MarkStatus = "added" | "removed" | "modified" | "unchanged";

export interface MarkedTextProps {
  text: string;
  /** This sentence's own word-level spans (old side: equal + delete; new side: equal + insert). */
  spans?: DiffSpan[] | null;
  side: "old" | "new";
  status: MarkStatus;
  /**
   * Show only the exact window [start, end) of the sentence (lib/snippet.ts). A visible "… "
   * leads when start > 0 and " …" trails when end < text length. Omitted: the whole sentence.
   */
  start?: number;
  end?: number;
}

function splitWhitespace(text: string): [string, string, string] {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
  return m ? [m[1], m[2], m[3]] : ["", text, ""];
}

function Ellipsis({ lead }: { lead: boolean }) {
  return (
    <span className="font-sans text-ink-secondary">
      {lead ? "… " : " …"}
      <span className="sr-only">{lead ? "(sentence begins earlier) " : " (sentence continues)"}</span>
    </span>
  );
}

function Body({ text, spans, side, status }: { text: string; spans: DiffSpan[] | null | undefined; side: "old" | "new"; status: MarkStatus }) {
  if (status === "added" && side === "new") {
    return (
      <mark className="hl">
        <span className="sr-only">new this year: </span>
        {text}
      </mark>
    );
  }
  if (status === "removed" && side === "old") {
    return (
      <del className="strike">
        <span className="sr-only">removed this year: </span>
        {text}
      </del>
    );
  }
  if (status === "modified" && spans && spans.length > 0) {
    return (
      <>
        {spans.map((span, i) => {
          if (span.op === "equal") return <span key={i}>{span.text}</span>;
          const [lead, core, trail] = splitWhitespace(span.text);
          // Punctuation- or spacing-only edits are not word changes: drawn as plain text.
          if (!core || !hasWordChars(core)) return <span key={i}>{span.text}</span>;
          if (span.op === "insert") {
            return (
              <span key={i}>
                {lead}
                <mark className="hl">
                  <span className="sr-only">new: </span>
                  {core}
                </mark>
                {trail}
              </span>
            );
          }
          return (
            <span key={i}>
              {lead}
              <del className="strike">
                <span className="sr-only">removed: </span>
                {core}
              </del>
              {trail}
            </span>
          );
        })}
      </>
    );
  }
  return <>{text}</>;
}

export function MarkedText({ text, spans, side, status, start, end }: MarkedTextProps) {
  const n = text.length;
  const from = Math.max(0, Math.min(start ?? 0, n));
  const to = Math.max(from, Math.min(end ?? n, n));
  const windowed = from > 0 || to < n;
  const merged = spans && spans.length > 0 ? mergeChangedSpans(spans) : null;
  const shownSpans = merged && windowed ? sliceSpans(merged, from, to) : merged;
  return (
    <>
      {from > 0 ? <Ellipsis lead /> : null}
      <Body text={windowed ? text.slice(from, to) : text} spans={shownSpans} side={side} status={status} />
      {to < n ? <Ellipsis lead={false} /> : null}
    </>
  );
}
