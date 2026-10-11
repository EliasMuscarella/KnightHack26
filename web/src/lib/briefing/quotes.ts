/**
 * Verbatim quotes for the briefing. Every quote's text is `sentence_index[id].text`, looked up
 * by sentence id; marks come only from the deterministic diff (a sentence's `diff_spans`) or from
 * the trends payload's character offsets of newly added words. Nothing is paraphrased.
 */
import { textFragmentUrl } from "@/lib/format";
import type { Change, Comparison, DiffSpan, SentenceLocation } from "@/types/comparison";

import type { MarkedQuote } from "./types";

/** Only filings on the SEC's own site are ever linked (FilingLink applies the same rule). */
const SEC_DOCUMENT = /^https:\/\/www\.sec\.gov\//;

/**
 * Where a quoted sentence lives: a deep link to exactly that sentence in its own filing (the old
 * filing for a last-year sentence, the new filing for a this-year one, by the sentence's `side`)
 * and that filing's fiscal year. The link is the filing's EDGAR URL plus a URL text fragment of the
 * sentence (`textFragmentUrl`), so a supporting browser scrolls to and highlights it; others open
 * the document. No link for FIXTURE data or a URL outside https://www.sec.gov/.
 */
export function sentenceSource(comparison: Comparison, loc: Pick<SentenceLocation, "side" | "text">): Pick<MarkedQuote, "href" | "fiscalYear"> {
  const filing = loc.side === "old" ? comparison.old_filing : comparison.new_filing;
  const url = filing?.edgar_url ?? "";
  const linkable = comparison.is_fixture !== true && SEC_DOCUMENT.test(url) && loc.text.trim() !== "";
  return { href: linkable ? textFragmentUrl(url, loc.text) : null, fiscalYear: filing?.fiscal_year ?? null };
}

/**
 * `[start, end)` character offsets of marked words -> `DiffSpan[]` segments that cover the whole
 * text (`equal` between marks, `insert` for marks). Offsets are clamped, sorted and merged when
 * they overlap or touch. Null when nothing valid is marked.
 */
export function spansFromOffsets(text: string, offsets: readonly (readonly [number, number])[] | null | undefined): DiffSpan[] | null {
  const n = text.length;
  const ranges = (offsets ?? [])
    .map(([a, b]) => [Math.max(0, Math.min(n, Math.trunc(a))), Math.max(0, Math.min(n, Math.trunc(b)))] as [number, number])
    .filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b) && b > a)
    .sort((p, q) => p[0] - q[0] || p[1] - q[1]);
  if (ranges.length === 0) return null;
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  const out: DiffSpan[] = [];
  let pos = 0;
  for (const [a, b] of merged) {
    if (a > pos) out.push({ op: "equal", text: text.slice(pos, a) });
    out.push({ op: "insert", text: text.slice(a, b) });
    pos = b;
  }
  if (pos < n) out.push({ op: "equal", text: text.slice(pos) });
  return out;
}

/**
 * The marked quote for sentence `id`: text from the sentence index; spans from the change's
 * sentence record (its `diff_spans` for a modified sentence, the whole sentence as one insert or
 * delete for an added or removed one, null for an unchanged one or a sentence outside the change).
 * Null when the id is missing or not in the index.
 */
export function quoteById(comparison: Comparison, change: Change | undefined, id: string | null | undefined): MarkedQuote | null {
  if (!id) return null;
  const loc = comparison.sentence_index[id];
  if (!loc) return null;
  const text = loc.text;
  let spans: DiffSpan[] | null = null;
  const s = change?.sentences.find((x) => x.id === id);
  if (s && s.text === text) {
    if (s.diff_spans && s.diff_spans.length > 0 && s.diff_spans.map((x) => x.text).join("") === text) {
      spans = s.diff_spans.map((x) => ({ op: x.op, text: x.text }));
    } else if (s.status === "added" && text) {
      spans = [{ op: "insert", text }];
    } else if (s.status === "removed" && text) {
      spans = [{ op: "delete", text }];
    }
  }
  return { sentenceId: id, text, spans, ...sentenceSource(comparison, loc) };
}
