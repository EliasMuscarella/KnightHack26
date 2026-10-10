/**
 * Display rules for modified sentence pairs. What changed is decided by the pipeline
 * (`diff_spans`); these helpers only choose how to draw it.
 */
import type { DiffSpan, Sentence } from "@/types/comparison";

/**
 * When more than this share of a modified pair's words changed, word-level markup is harder
 * to read than the two sentences themselves, so the pair is drawn as a replacement
 * ("Rewritten"): last year's sentence fully struck through, this year's fully highlighted.
 *
 * ratio = (deleted words + inserted words) / (words in old sentence + words in new sentence),
 * counting word tokens only (whitespace- and punctuation-only spans count zero).
 */
export const REPLACEMENT_THRESHOLD = 0.5;

const WORD_RE = /[\p{L}\p{N}]+(?:['’.\-][\p{L}\p{N}]+)*/gu;

export function wordCount(text: string): number {
  return (text.match(WORD_RE) ?? []).length;
}

function spanWords(spans: DiffSpan[] | null | undefined, op: DiffSpan["op"]): number {
  return (spans ?? []).filter((s) => s.op === op).reduce((n, s) => n + wordCount(s.text), 0);
}

/** Changed-token ratio of an aligned (old, new) modified pair; null when it cannot be computed. */
export function changedTokenRatio(oldS: Sentence, newS: Sentence): number | null {
  const total = wordCount(oldS.text) + wordCount(newS.text);
  if (total === 0) return null;
  return (spanWords(oldS.diff_spans, "delete") + spanWords(newS.diff_spans, "insert")) / total;
}

/** Ids of the sentences (both sides) of every modified pair drawn as a replacement. */
export function rewrittenIds(sentences: Sentence[]): Set<string> {
  const byId = new Map(sentences.map((s) => [s.id, s] as const));
  const out = new Set<string>();
  for (const s of sentences) {
    if (s.side !== "old" || s.status !== "modified" || !s.counterpart_id) continue;
    const n = byId.get(s.counterpart_id);
    if (!n || n.status !== "modified") continue;
    const r = changedTokenRatio(s, n);
    if (r !== null && r > REPLACEMENT_THRESHOLD) {
      out.add(s.id);
      out.add(n.id);
    }
  }
  return out;
}

/** Character offset just past the last changed span (insert or delete), or 0 when none. */
export function lastMarkedOffset(spans: DiffSpan[] | null | undefined): number {
  let pos = 0;
  let last = 0;
  for (const s of spans ?? []) {
    pos += s.text.length;
    if (s.op !== "equal") last = pos;
  }
  return last;
}

/**
 * Merges runs of same-op changed spans that are separated only by whitespace, so a changed
 * phrase gets one marker instead of one per word. Concatenated text is unchanged.
 */
export function mergeChangedSpans(spans: DiffSpan[]): DiffSpan[] {
  const out: DiffSpan[] = [];
  for (let i = 0; i < spans.length; i++) {
    const cur = spans[i];
    const last = out[out.length - 1];
    if (cur.op !== "equal" && last && last.op === cur.op) {
      last.text += cur.text;
      continue;
    }
    if (cur.op === "equal" && /^\s+$/.test(cur.text) && last && last.op !== "equal") {
      const nxt = spans[i + 1];
      if (nxt && nxt.op === last.op) {
        last.text += cur.text + nxt.text;
        i += 1;
        continue;
      }
    }
    out.push({ ...cur });
  }
  return out;
}
