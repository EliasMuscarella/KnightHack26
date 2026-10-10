/**
 * Snippet windows for verbatim filing quotes. A long sentence is shown as a window of at most
 * `max` characters that always contains the evidence (the changed words, or the topic term),
 * snapped to word boundaries. The quote itself is never edited: the window is an exact slice of
 * the sentence, every trimmed side gets a visible ellipsis (the caller draws it), and the full
 * sentence is always one click away.
 *
 * `snippetWindow` is a character-for-character port of `snippet_window` in
 * scripts/check_integrity.py; tests/fixtures/snippet_vectors.json pins the parity. Pure, no
 * imports at runtime, unit-tested with node --test.
 */

/** A half-open character range [start, end) inside a sentence's own text. */
export type Range = [number, number];

export interface SnippetWindow {
  start: number;
  end: number;
}

/** Topic examples on the Trends page show up to this many characters. */
export const TOPIC_EXAMPLE_MAX = 320;

/** The earliest span in tuple order (by start, then end), like Python's `min` over tuples. */
function earliest(evidence: readonly Range[]): Range {
  let best = evidence[0];
  for (const r of evidence) if (r[0] < best[0] || (r[0] === best[0] && r[1] < best[1])) best = r;
  return best;
}

/** Last index of a space in [from, to), or -1 (Python `text.rfind(" ", from, to)`). */
function lastSpaceIn(text: string, from: number, to: number): number {
  if (to - 1 < from) return -1;
  const i = text.lastIndexOf(" ", to - 1);
  return i >= from ? i : -1;
}

/**
 * A window of at most `max` characters that contains the earliest evidence span, with the span
 * about a third of the way in, starting at a word start and ending right before a space (or at
 * the span end). A span longer than the window is shown from its start.
 */
export function snippetWindow(text: string, evidence: readonly Range[] | null | undefined, max = 220, context = 40): SnippetWindow {
  const n = text.length;
  if (n <= max) return { start: 0, end: n };
  let [a, b] = evidence && evidence.length > 0 ? earliest(evidence) : [0, 0];
  a = Math.max(0, Math.min(a, n));
  b = Math.max(a, Math.min(b, n));
  const longSpan = b - a >= max;
  let start: number;
  if (longSpan) {
    start = a;
  } else {
    start = Math.max(0, a - Math.max(context, Math.floor((max - (b - a)) / 3)));
    start = Math.min(start, Math.max(0, n - max)); // the window stays inside the text
    if (start + max < b) start = b - max; // the span's end must fit
    start = Math.min(start, a); // never past the span start
  }
  if (start > 0) start = lastSpaceIn(text, 0, start) + 1; // a word start at or before `start`
  let end = Math.min(n, start + max);
  if (!longSpan && end < b) {
    // the backward snap pushed the span out: move the start forward
    end = b;
    const nxt = text.indexOf(" ", Math.max(0, end - max));
    start = Math.min(nxt !== -1 ? nxt + 1 : start, a);
  }
  if (end < n) {
    // snap the end back to a word end
    const prev = lastSpaceIn(text, start, end);
    if (prev !== -1 && (longSpan || prev >= b)) end = prev;
  }
  return { start, end };
}

/** The minimal shape of a sentence record needed to locate its marked words. */
export interface MarkableSentence {
  text: string;
  status?: string | null;
  diff_spans?: readonly { op: string; text: string }[] | null;
}

/**
 * Character ranges of `op` ("insert" | "delete") spans inside a sentence's own text, whitespace
 * trimmed, adjacent runs (separated only by whitespace) merged; the whole sentence for an added
 * sentence (insert) or a removed one (delete). Port of `marked_spans` in scripts/check_integrity.py.
 */
export function markedRanges(sentence: MarkableSentence, op: "insert" | "delete"): Range[] {
  const text = sentence.text ?? "";
  const status = sentence.status;
  if ((op === "insert" && status === "added") || (op === "delete" && status === "removed")) return text ? [[0, text.length]] : [];
  const out: Range[] = [];
  let pos = 0;
  for (const sp of sentence.diff_spans ?? []) {
    const end = pos + sp.text.length;
    if (sp.op === op) {
      const seg = text.slice(pos, end);
      const a = pos + (seg.length - seg.trimStart().length);
      const b = end - (seg.length - seg.trimEnd().length);
      if (b > a) {
        const last = out[out.length - 1];
        if (last && !text.slice(last[1], a).trim()) last[1] = b;
        else out.push([a, b]);
      }
    }
    pos = end;
  }
  return out;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\/]/g, (c) => `\\${c}`);
}

/**
 * Whole-word, case-insensitive matcher for a term: words joined by any whitespace or a hyphen,
 * straight or curly apostrophes, never inside a longer word. Port of `term_regex` in
 * pipeline/trends/derive.py.
 */
export function termRegex(term: string): RegExp | null {
  const words = term.split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;
  const parts = words.map((w) => escapeRegex(w).replace(/'/g, "['’]"));
  try {
    return new RegExp(`(?<![\\p{L}\\p{N}_])${parts.join("(?:\\s*-\\s*|\\s+)")}(?![\\p{L}\\p{N}_])`, "giu");
  } catch {
    return null;
  }
}

/** Every occurrence of `term` in `text` as a character range. */
export function termOccurrences(term: string, text: string): Range[] {
  const rx = termRegex(term);
  if (!rx) return [];
  const out: Range[] = [];
  for (const m of text.matchAll(rx)) {
    if (m.index === undefined || m[0].length === 0) continue;
    out.push([m.index, m.index + m[0].length]);
  }
  return out;
}

/**
 * Evidence for a topic example: the occurrences of the matched terms that lie inside the added
 * spans (any occurrence when the example has no spans), else the added spans themselves. The
 * window then shows the earliest one, so the displayed quote always contains its topic term.
 */
export function topicEvidence(text: string, terms: readonly string[] | null | undefined, addedSpans: readonly Range[] | null | undefined): Range[] {
  const spans = addedSpans ?? [];
  const anchors: Range[] = [];
  for (const term of terms ?? []) {
    for (const o of termOccurrences(term, text)) {
      if (spans.length === 0 || spans.some(([a, b]) => a <= o[0] && o[1] <= b)) anchors.push(o);
    }
  }
  anchors.sort((p, q) => p[0] - q[0] || p[1] - q[1]);
  return anchors.length > 0 ? anchors : [...spans];
}

/** A displayed window over a sentence: the slice bounds and whether each side was trimmed. */
export interface Snippet extends SnippetWindow {
  /** True when text before `start` is hidden (draw a leading ellipsis). */
  leading: boolean;
  /** True when text after `end` is hidden (draw a trailing ellipsis). */
  trailing: boolean;
}

/** `snippetWindow` plus the trimmed-side flags; never throws on missing evidence. */
export function snippet(text: string | null | undefined, evidence: readonly Range[] | null | undefined, max = 220): Snippet {
  const t = text ?? "";
  const w = snippetWindow(t, evidence ?? [], max);
  return { ...w, leading: w.start > 0, trailing: w.end < t.length };
}

/** The minimal shape of a Trends "potential became actual" row (spans may be missing in old payloads). */
export interface ActualPairLike {
  old_text?: string | null;
  new_text?: string | null;
  old_spans?: readonly Range[] | null;
  new_spans?: readonly Range[] | null;
}

/**
 * Windows for both sides of a Trends "potential became actual" row: the evidence is each side's
 * own marked ranges (old: removed words, new: added words). A side without text is null. Missing
 * span fields (older API or store rows) fall back to the start of the sentence; never throws.
 */
export function actualSnippets(a: ActualPairLike, max = 220): { old: Snippet | null; new: Snippet | null } {
  return {
    old: a.old_text ? snippet(a.old_text, a.old_spans ?? [], max) : null,
    new: a.new_text ? snippet(a.new_text, a.new_spans ?? [], max) : null,
  };
}
