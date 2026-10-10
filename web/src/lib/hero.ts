/**
 * The home hero shows one real before/after from the library, chosen deterministically:
 * the top-ranked "Potential became actual" highlight across current reports, ties broken by
 * the parent change's score (desc), then ticker (asc), then the highlight's position. Nothing
 * is hardcoded; with no such highlight anywhere, the first highlight of the alphabetically first
 * company is used, and with no highlights at all the hero shows nothing.
 */
import type { Change, Comparison, Highlight } from "@/types/comparison";

export interface HeroPick {
  comparison: Comparison;
  change: Change;
  highlight: Highlight;
  /** Index of the highlight in its report (the last tie-breaker). */
  position: number;
}

function candidates(comparisons: Comparison[], kind: Highlight["kind"] | null): HeroPick[] {
  const out: HeroPick[] = [];
  for (const comparison of comparisons) {
    if (comparison.is_fixture) continue;
    const byId = new Map(comparison.changes.map((c) => [c.id, c] as const));
    (comparison.highlights ?? []).forEach((highlight, position) => {
      if (kind && highlight.kind !== kind) return;
      const change = byId.get(highlight.change_id);
      if (!change) return;
      out.push({ comparison, change, highlight, position });
    });
  }
  return out;
}

function compare(a: HeroPick, b: HeroPick): number {
  if (a.change.score !== b.change.score) return b.change.score - a.change.score;
  const t = a.comparison.company.ticker.localeCompare(b.comparison.company.ticker);
  if (t !== 0) return t;
  return a.position - b.position;
}

export function pickHero(comparisons: Comparison[]): HeroPick | null {
  const actual = candidates(comparisons, "potential_became_actual").sort(compare);
  if (actual.length > 0) return actual[0];
  const any = candidates(comparisons, null).sort(compare);
  return any[0] ?? null;
}
