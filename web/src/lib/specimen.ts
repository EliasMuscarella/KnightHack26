/**
 * The home hero's rotating specimens: one real before/after per kind of highlight, chosen
 * deterministically from the published reports (fixtures never). Same reports in, same slides out.
 *
 * Per kind the candidates are ranked by the parent change's score (desc), then ticker (asc), then the
 * highlight's position; a before/after pair needs an alignment similarity of at least
 * MIN_PAIR_SIMILARITY on both sides; a company that already has a slide is passed over while another company
 * has a candidate, and one risk factor never appears twice. Sentences longer than MAX_SIDE_CHARS are
 * skipped so a slide never needs a "Show full sentence" control (the panel stays one fixed height).
 */
import type { Change, Comparison, Highlight } from "@/types/comparison";

export type SpecimenKind = Highlight["kind"];

/** Order of the slides. */
export const SPECIMEN_KINDS: readonly SpecimenKind[] = [
  "potential_became_actual",
  "new_figure",
  "new_named_party",
  "new_risk",
  "removed_risk",
];

export const MAX_SIDE_CHARS = 240;

/** A before/after pair must be one sentence edited, not two sentences the aligner paired loosely. */
export const MIN_PAIR_SIMILARITY = 0.7;

export interface SpecimenSide {
  text: string;
  status: "added" | "removed" | "modified" | "unchanged";
  spans: Change["sentences"][number]["diff_spans"] | null;
}

export interface Specimen {
  kind: SpecimenKind;
  /** A figure that changed (both sides present) rather than appeared. */
  figureChanged: boolean;
  /** The signal value behind the highlight ("$4.5 billion", "Groq"), if any. */
  detail: string | null;
  ticker: string;
  /** Official SEC name; the caller maps it to a display name. */
  company: string;
  oldFY: number;
  newFY: number;
  changeId: string;
  shortTitle: string;
  title: string;
  old: SpecimenSide | null;
  new: SpecimenSide | null;
}

function side(comparison: Comparison, change: Change, id: string | null | undefined): SpecimenSide | null {
  if (!id) return null;
  const s = change.sentences.find((x) => x.id === id);
  if (s) return { text: s.text, status: s.status, spans: s.diff_spans ?? null };
  const loc = comparison.sentence_index[id];
  return loc ? { text: loc.text, status: "unchanged", spans: null } : null;
}

interface Candidate {
  specimen: Specimen;
  score: number;
  position: number;
}

function candidates(comparisons: readonly Comparison[], kind: SpecimenKind): Candidate[] {
  const out: Candidate[] = [];
  for (const comparison of comparisons) {
    if (comparison.is_fixture) continue;
    const byId = new Map(comparison.changes.map((c) => [c.id, c] as const));
    (comparison.highlights ?? []).forEach((h, position) => {
      if (h.kind !== kind) return;
      const change = byId.get(h.change_id);
      if (!change) return;
      const old = side(comparison, change, h.old_sentence_id);
      const next = side(comparison, change, h.new_sentence_id);
      if (!old && !next) return;
      if (old && next) {
        const sim = (id: string | null | undefined) => change.sentences.find((x) => x.id === id)?.alignment_similarity;
        const a = sim(h.old_sentence_id);
        const b = sim(h.new_sentence_id);
        if (typeof a !== "number" || typeof b !== "number" || a < MIN_PAIR_SIMILARITY || b < MIN_PAIR_SIMILARITY) return;
      }
      if ((old && old.text.length > MAX_SIDE_CHARS) || (next && next.text.length > MAX_SIDE_CHARS)) return;
      out.push({
        score: change.score,
        position,
        specimen: {
          kind,
          figureChanged: kind === "new_figure" && !!old && !!next,
          detail: h.detail?.trim() || null,
          ticker: comparison.company.ticker,
          company: comparison.company.name,
          oldFY: comparison.old_filing.fiscal_year,
          newFY: comparison.new_filing.fiscal_year,
          changeId: change.id,
          shortTitle: change.short_title,
          title: change.title,
          old,
          new: next,
        },
      });
    });
  }
  return out.sort((a, b) => b.score - a.score || a.specimen.ticker.localeCompare(b.specimen.ticker) || a.position - b.position);
}

export function pickSpecimens(comparisons: readonly Comparison[]): Specimen[] {
  const out: Specimen[] = [];
  const tickers = new Set<string>();
  const changes = new Set<string>();
  for (const kind of SPECIMEN_KINDS) {
    const list = candidates(comparisons, kind).filter((c) => !changes.has(`${c.specimen.ticker}:${c.specimen.changeId}`));
    const pick = list.find((c) => !tickers.has(c.specimen.ticker)) ?? list[0];
    if (!pick) continue;
    out.push(pick.specimen);
    tickers.add(pick.specimen.ticker);
    changes.add(`${pick.specimen.ticker}:${pick.specimen.changeId}`);
  }
  return out;
}
