/**
 * A verbatim filing sentence drawn the way an analyst marks up a printed 10-K (DESIGN.md):
 * this year's added or changed words carry the highlighter; last year's removed words are
 * struck through. Only spans the deterministic diff produced are ever marked. Text is rendered
 * as text; nothing is injected as HTML. Server-safe (no hooks).
 */
import type { DiffSpan } from "@/types/comparison";

import { mergeChangedSpans } from "@/lib/diffDisplay";

export type MarkStatus = "added" | "removed" | "modified" | "unchanged";

export interface MarkedTextProps {
  text: string;
  /** This sentence's own word-level spans (old side: equal + delete; new side: equal + insert). */
  spans?: DiffSpan[] | null;
  side: "old" | "new";
  status: MarkStatus;
  /** Show at most this many characters (an exact prefix); the caller adds the ellipsis control. */
  limit?: number;
}

/** Cuts a span list to an exact character prefix without altering any text. */
export function cutSpans(spans: DiffSpan[], limit: number): DiffSpan[] {
  const out: DiffSpan[] = [];
  let used = 0;
  for (const s of spans) {
    if (used >= limit) break;
    const take = Math.min(s.text.length, limit - used);
    out.push({ op: s.op, text: s.text.slice(0, take) });
    used += take;
  }
  return out;
}

function splitWhitespace(text: string): [string, string, string] {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
  return m ? [m[1], m[2], m[3]] : ["", text, ""];
}

export function MarkedText({ text, spans, side, status, limit }: MarkedTextProps) {
  const shown = limit !== undefined && limit < text.length ? text.slice(0, limit) : text;
  if (status === "added" && side === "new") {
    return (
      <mark className="hl">
        <span className="sr-only">new this year: </span>
        {shown}
      </mark>
    );
  }
  if (status === "removed" && side === "old") {
    return (
      <del className="strike">
        <span className="sr-only">removed this year: </span>
        {shown}
      </del>
    );
  }
  if (status === "modified" && spans && spans.length > 0) {
    const merged = mergeChangedSpans(spans);
    const list = limit !== undefined && limit < text.length ? cutSpans(merged, limit) : merged;
    return (
      <>
        {list.map((span, i) => {
          if (span.op === "equal") return <span key={i}>{span.text}</span>;
          const [lead, core, trail] = splitWhitespace(span.text);
          if (!core) return <span key={i}>{span.text}</span>;
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
  return <>{shown}</>;
}
