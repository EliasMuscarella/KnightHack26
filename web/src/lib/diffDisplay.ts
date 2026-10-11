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

// ---------------------------------------------------------------------------------------
// Safety net: changes of case, whitespace or punctuation only are drawn as unchanged text.
// ---------------------------------------------------------------------------------------

const ALNUM_RE = /[\p{L}\p{N}]/u;
const NON_ALNUM_RE = /[^\p{L}\p{N}]+/gu;

/** True when a changed span carries at least one letter or digit (otherwise it is drawn plain). */
export function hasWordChars(text: string | null | undefined): boolean {
  return ALNUM_RE.test(text ?? "");
}

/** Casefolded letters and digits only: "The," and "the" share the key "the". */
export function alnumKey(text: string | null | undefined): string {
  return (text ?? "").toLowerCase().replace(NON_ALNUM_RE, "");
}

/** Relabels matched insert/delete spans as "equal" (case-, space- or punctuation-only edits). */
function neutralizeLevel(oldSpans: DiffSpan[], newSpans: DiffSpan[]): void {
  const deletes = new Map<string, number[]>();
  oldSpans.forEach((s, i) => {
    if (s.op !== "delete") return;
    const k = alnumKey(s.text);
    if (!k) return;
    const list = deletes.get(k) ?? [];
    list.push(i);
    deletes.set(k, list);
  });
  newSpans.forEach((s, i) => {
    if (s.op !== "insert") return;
    const k = alnumKey(s.text);
    const list = k ? deletes.get(k) : undefined;
    if (!list || list.length === 0) return;
    const j = list.shift() as number;
    oldSpans[j] = { op: "equal", text: oldSpans[j].text };
    newSpans[i] = { op: "equal", text: s.text };
  });
}

/**
 * For an aligned (old, new) pair: an inserted span whose casefolded letters and digits equal a
 * deleted span's on the other side differs only in case, spacing or punctuation, so both are
 * drawn as plain text. Matched first span by span, then over merged runs. Returns new lists
 * (merged); the concatenated text of each side is unchanged.
 */
export function neutralizeCaseOnly(
  oldSpans: DiffSpan[] | null | undefined,
  newSpans: DiffSpan[] | null | undefined,
): { old: DiffSpan[]; new: DiffSpan[] } {
  const o = (oldSpans ?? []).map((s) => ({ ...s }));
  const n = (newSpans ?? []).map((s) => ({ ...s }));
  neutralizeLevel(o, n);
  const om = mergeChangedSpans(o);
  const nm = mergeChangedSpans(n);
  neutralizeLevel(om, nm);
  return { old: om, new: nm };
}

/**
 * Display spans for every sentence of a change: modified pairs (old side + its counterpart) get
 * `neutralizeCaseOnly`; everything else keeps its own spans. Keyed by sentence id.
 */
export function pairDisplaySpans(sentences: Sentence[]): Map<string, DiffSpan[] | null> {
  const byId = new Map(sentences.map((s) => [s.id, s] as const));
  const out = new Map<string, DiffSpan[] | null>();
  for (const s of sentences) out.set(s.id, s.diff_spans ?? null);
  for (const s of sentences) {
    if (s.side !== "old" || s.status !== "modified" || !s.counterpart_id) continue;
    const n = byId.get(s.counterpart_id);
    if (!n || n.side !== "new" || n.status !== "modified") continue;
    const pair = neutralizeCaseOnly(s.diff_spans, n.diff_spans);
    out.set(s.id, pair.old);
    out.set(n.id, pair.new);
  }
  return out;
}

/** Character ranges whose text has letters or digits (punctuation-only ranges are drawn plain). */
export function wordRanges(text: string, ranges: readonly [number, number][] | null | undefined): [number, number][] {
  return (ranges ?? []).filter(([a, b]) => hasWordChars(text.slice(a, b))).map(([a, b]) => [a, b] as [number, number]);
}

/**
 * Character-range version of `neutralizeCaseOnly` (Trends rows carry ranges, not spans): an
 * inserted range on the new side whose casefolded letters and digits equal a deleted range's on
 * the old side is dropped from both. Punctuation-only ranges are dropped too.
 */
export function neutralizeRangePair(
  oldText: string | null | undefined,
  oldRanges: readonly [number, number][] | null | undefined,
  newText: string | null | undefined,
  newRanges: readonly [number, number][] | null | undefined,
): { old: [number, number][]; new: [number, number][] } {
  const ot = oldText ?? "";
  const nt = newText ?? "";
  const o = wordRanges(ot, oldRanges);
  const n = wordRanges(nt, newRanges);
  const dropOld = new Set<number>();
  const dropNew = new Set<number>();
  n.forEach(([a, b], i) => {
    const k = alnumKey(nt.slice(a, b));
    const j = o.findIndex(([c, d], idx) => !dropOld.has(idx) && alnumKey(ot.slice(c, d)) === k);
    if (k && j >= 0) {
      dropOld.add(j);
      dropNew.add(i);
    }
  });
  return { old: o.filter((_, i) => !dropOld.has(i)), new: n.filter((_, i) => !dropNew.has(i)) };
}

/** Cuts a span list to the exact character window [start, end) without altering any text. */
export function sliceSpans(spans: readonly DiffSpan[], start: number, end: number): DiffSpan[] {
  const out: DiffSpan[] = [];
  let pos = 0;
  for (const s of spans) {
    const a = pos;
    const b = pos + s.text.length;
    pos = b;
    const from = Math.max(a, start);
    const to = Math.min(b, end);
    if (to > from) out.push({ op: s.op, text: s.text.slice(from - a, to - a) });
  }
  return out;
}
