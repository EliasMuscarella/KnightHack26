/**
 * Display vocabulary: the ONE place where internal contract keys become reader-facing words.
 * Contract field names never change; only what the UI calls them. Badges, filters, tooltips,
 * score lines and cards all read from here.
 *
 * Neutral wording only: a change in disclosure language is not a change in actual risk.
 */
import type { ChangeType, Highlight, SignalHit } from "@/types/comparison";

// ---------------------------------------------------------------------------------------
// Change types
// ---------------------------------------------------------------------------------------

export interface ChangeTypeVocab {
  label: string;
  helper: string;
  /** Text marker shown next to the label so meaning never depends on color alone. */
  marker: string;
  /** Tailwind classes for the badge (background, text, border). */
  badgeClass: string;
}

/** Display order for filters and counts. */
export const CHANGE_TYPE_ORDER: ChangeType[] = [
  "new",
  "materially_reworded",
  "expanded",
  "reduced",
  "removed",
  "largely_unchanged",
];

export const CHANGE_TYPE_VOCAB: Record<ChangeType, ChangeTypeVocab> = {
  new: {
    label: "New risk",
    helper: "Appears only in this year's filing.",
    marker: "+",
    badgeClass: "bg-add-bg text-add-fg border-add-line",
  },
  removed: {
    label: "Dropped risk",
    helper: "Appeared last year, not this year.",
    marker: "−",
    badgeClass: "bg-del-bg text-del-fg border-del-line",
  },
  expanded: {
    label: "Expanded",
    helper: "Substantially more language this year.",
    marker: "↗",
    badgeClass: "bg-exp-bg text-exp-fg border-exp-line",
  },
  reduced: {
    label: "Scaled back",
    helper: "Substantially less language this year.",
    marker: "↘",
    badgeClass: "bg-red-bg text-red-fg border-red-line",
  },
  materially_reworded: {
    label: "Major update",
    helper: "Substantially rewritten from last year.",
    marker: "~",
    badgeClass: "bg-mod-bg text-mod-fg border-mod-line",
  },
  largely_unchanged: {
    label: "Essentially unchanged",
    helper: "Little or no change in wording from last year.",
    marker: "=",
    badgeClass: "bg-neutral-bg text-ink-muted border-line-strong",
  },
};

export function changeTypeVocab(t: string): ChangeTypeVocab {
  return (
    CHANGE_TYPE_VOCAB[t as ChangeType] ?? {
      label: t.replace(/_/g, " "),
      helper: "",
      marker: "•",
      badgeClass: "bg-neutral-bg text-ink-muted border-line-strong",
    }
  );
}

/** Every change type except "largely_unchanged" counts as a meaningful change. */
export function meaningfulCount(byChangeType: Record<string, number> | null | undefined): { meaningful: number; unchanged: number; total: number } {
  const counts = byChangeType ?? {};
  const total = Object.values(counts).reduce((s, n) => s + (typeof n === "number" ? n : 0), 0);
  const unchanged = counts.largely_unchanged ?? 0;
  return { meaningful: total - unchanged, unchanged, total };
}

// ---------------------------------------------------------------------------------------
// Deterministic signals (score lines, highlight kinds)
// ---------------------------------------------------------------------------------------

export interface TermVocab {
  label: string;
  helper: string;
}

export const SIGNAL_VOCAB: Record<string, TermVocab> = {
  hypothetical_to_actual: {
    label: "Potential → Actual",
    helper:
      "Last year this was described as something that could happen. This year it is described as something that has happened.",
  },
  new_quantities: {
    label: "New figure disclosed",
    helper: "A dollar amount, percentage, or count that wasn't in last year's version.",
  },
  new_entities: {
    label: "Newly named",
    helper: "A country, regulator, law, or company named for the first time in this risk factor.",
  },
  added_text_ratio: {
    label: "Large share of new text",
    helper: "A large part of this year's version is new language.",
  },
  semantic_shift: {
    label: "Meaning shifted noticeably",
    helper: "The overall wording moved well away from last year's version.",
  },
};

/**
 * "New figure disclosed" is only accurate when last year's version had no counterpart
 * sentence. When a figure sits in a sentence that also existed last year (40% → 30%), the
 * figure changed rather than appeared.
 */
export const FIGURE_CHANGED: TermVocab = {
  label: "Figure changed",
  helper: "A dollar amount, percentage, or count that changed from last year's version.",
};

/** Mixed case for a score line or list: some figures are new, some changed. */
export const FIGURE_NEW_OR_CHANGED: TermVocab = {
  label: "New or changed figures",
  helper: "Dollar amounts, percentages, or counts that are new or changed from last year's version.",
};

export type FigureVariant = "new" | "changed" | "mixed";

/** A figure hit with a last-year sentence is a changed figure; without one it is new. */
export function figureVariant(hits: Pick<SignalHit, "old_sentence_ids" | "new_sentence_ids">[] | null | undefined): FigureVariant {
  const list = hits ?? [];
  if (list.length === 0) return "new";
  const changed = list.filter((h) => (h.old_sentence_ids ?? []).length > 0 && (h.new_sentence_ids ?? []).length > 0).length;
  if (changed === 0) return "new";
  return changed === list.length ? "changed" : "mixed";
}

export function figureVocab(variant: FigureVariant): TermVocab {
  if (variant === "changed") return FIGURE_CHANGED;
  if (variant === "mixed") return FIGURE_NEW_OR_CHANGED;
  return SIGNAL_VOCAB.new_quantities;
}

export const HIGHLIGHT_KIND_VOCAB: Record<Highlight["kind"], TermVocab & { badgeClass: string; marker: string }> = {
  // No glyph: the label already carries the arrow, and a "!" read as an alert.
  potential_became_actual: { ...SIGNAL_VOCAB.hypothetical_to_actual, marker: "", badgeClass: "bg-surface text-mod-fg border-mod-line" },
  new_figure: { ...SIGNAL_VOCAB.new_quantities, marker: "#", badgeClass: "bg-exp-bg text-exp-fg border-exp-line" },
  new_named_party: { ...SIGNAL_VOCAB.new_entities, marker: "@", badgeClass: "bg-exp-bg text-exp-fg border-exp-line" },
  new_risk: {
    label: CHANGE_TYPE_VOCAB.new.label,
    helper: CHANGE_TYPE_VOCAB.new.helper,
    marker: "+",
    badgeClass: CHANGE_TYPE_VOCAB.new.badgeClass,
  },
  removed_risk: {
    label: CHANGE_TYPE_VOCAB.removed.label,
    helper: CHANGE_TYPE_VOCAB.removed.helper,
    marker: "−",
    badgeClass: CHANGE_TYPE_VOCAB.removed.badgeClass,
  },
};

/** True for a `new_figure` highlight that has both a last-year and a this-year sentence. */
export function isFigureChanged(h: Pick<Highlight, "kind" | "old_sentence_id" | "new_sentence_id">): boolean {
  return h.kind === "new_figure" && !!h.old_sentence_id && !!h.new_sentence_id;
}

/**
 * Display vocabulary for a highlight. Pass `figureChanged` (both an old and a new sentence
 * id on a `new_figure` highlight) to get the "Figure changed" variant.
 */
export function highlightKindVocab(kind: string, figureChanged = false) {
  if (kind === "new_figure" && figureChanged) return { ...HIGHLIGHT_KIND_VOCAB.new_figure, ...FIGURE_CHANGED };
  return (
    HIGHLIGHT_KIND_VOCAB[kind as Highlight["kind"]] ?? {
      label: kind.replace(/_/g, " "),
      helper: "",
      marker: "•",
      badgeClass: "bg-neutral-bg text-ink-muted border-line-strong",
    }
  );
}

// ---------------------------------------------------------------------------------------
// AI checks (rubric questions in plain words)
// ---------------------------------------------------------------------------------------

/** Plain-language versions of the rubric questions (the exact wording is in Analyst details). */
export const RUBRIC_PLAIN: Record<string, string> = {
  q1: "Is something that could happen now described as having happened?",
  q2: "Is a new country, government, law, or company named?",
  q3: "Is a new financial or operational impact stated?",
  q4: "Was a previously disclosed exposure narrowed or removed?",
};

export const AI_CHECK_PREFIX = "AI check: ";
export const AI_CHECK_HELPER = "An AI model answered yes and cited the filing sentences that show it.";

/** Display label for a score line, from its machine key (`signal`). */
export function scoreLineLabel(signal: string, changeType: string, fallback: string, figures: FigureVariant = "new"): string {
  if (signal === "new_quantities") return figureVocab(figures).label;
  if (signal === "change_type" || signal.startsWith("change_type:")) {
    const t = signal.includes(":") ? signal.split(":")[1] : changeType;
    return changeTypeVocab(t).label;
  }
  const rubric = /^rubric_(q\d+)$/i.exec(signal);
  if (rubric) {
    const plain = RUBRIC_PLAIN[rubric[1].toLowerCase()];
    return AI_CHECK_PREFIX + (plain ?? fallback);
  }
  return SIGNAL_VOCAB[signal]?.label ?? fallback;
}

export function scoreLineHelper(signal: string, changeType: string, figures: FigureVariant = "new"): string {
  if (signal === "new_quantities") return figureVocab(figures).helper;
  if (signal === "change_type" || signal.startsWith("change_type:")) {
    const t = signal.includes(":") ? signal.split(":")[1] : changeType;
    return changeTypeVocab(t).helper;
  }
  if (/^rubric_q\d+$/i.test(signal)) return AI_CHECK_HELPER;
  return SIGNAL_VOCAB[signal]?.helper ?? "";
}

// ---------------------------------------------------------------------------------------
// Change level (the 0–100 score in words)
// ---------------------------------------------------------------------------------------

/** Score at or above this is "High". */
export const LEVEL_HIGH_MIN = 60;
/** Score at or above this (and below LEVEL_HIGH_MIN) is "Medium"; below it is "Low". */
export const LEVEL_MEDIUM_MIN = 25;

export type ChangeLevel = "High" | "Medium" | "Low";

export function changeLevel(score: number): ChangeLevel {
  if (score >= LEVEL_HIGH_MIN) return "High";
  if (score >= LEVEL_MEDIUM_MIN) return "Medium";
  return "Low";
}

export const CHANGE_LEVEL = {
  label: "Change level",
  /** Visible prefix on every level chip, so "High" never reads as a risk rating. */
  prefix: "Wording change",
  helper: "How much the language changed, not how risky the company is.",
  /** One-line note at the top of the "All changes" table. */
  tableNote: "Change level measures how much the wording changed. It is not a risk rating.",
} as const;

// ---------------------------------------------------------------------------------------
// Section names and fixed copy
// ---------------------------------------------------------------------------------------

export const AUDIT_TRAIL = "Audit trail";
export const ANALYST_DETAILS = "Analyst details";

export const AI_SUMMARY = {
  label: "AI summary",
  helper: "Generated from the two filings. Every point cites the sentences it is based on.",
} as const;

export const RISK_FACTORS = "Risk Factors";
