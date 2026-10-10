/** Lookups into a change's sentence records (status and word-level diff spans). */
import type { Change, Comparison, DiffSpan, Sentence } from "@/types/comparison";

export interface QuoteSource {
  text: string;
  status: Sentence["status"];
  spans: DiffSpan[] | null;
}

/** The sentence record of `id` inside `change`, or a plain record from the sentence index. */
export function quoteSource(comparison: Comparison, change: Change | undefined, id: string | null | undefined): QuoteSource | null {
  if (!id) return null;
  const s = change?.sentences.find((x) => x.id === id);
  if (s) return { text: s.text, status: s.status, spans: s.diff_spans ?? null };
  const loc = comparison.sentence_index[id];
  return loc ? { text: loc.text, status: "unchanged", spans: null } : null;
}
