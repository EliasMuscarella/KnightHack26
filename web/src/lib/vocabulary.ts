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

/**
 * Direction of a disclosure change (DESIGN.md). Color follows direction and nothing else:
 * blue = more language, orange = less language, ink = rewritten both ways.
 */
export type Direction = "more" | "less" | "rewrite" | "none";

export const DIRECTION_OF: Record<ChangeType, Direction> = {
  new: "more",
  expanded: "more",
  reduced: "less",
  removed: "less",
  materially_reworded: "rewrite",
  largely_unchanged: "none",
};

/** Tailwind classes from the design tokens: badge text, badge background, meter fill. */
export interface Tone {
  text: string;
  bg: string;
  fill: string;
}

export const CHANGE_TONE: Record<ChangeType, Tone> = {
  new: { text: "text-more-strong-fg", bg: "bg-more-strong-bg", fill: "bg-more-strong-fg" },
  expanded: { text: "text-more-fg", bg: "bg-more-bg", fill: "bg-more-fg" },
  removed: { text: "text-less-strong-fg", bg: "bg-less-strong-bg", fill: "bg-less-strong-fg" },
  reduced: { text: "text-less-fg", bg: "bg-less-bg", fill: "bg-less-mid" },
  materially_reworded: { text: "text-rewrite-fg", bg: "bg-rewrite-bg", fill: "bg-rewrite-mid" },
  largely_unchanged: { text: "text-ink-secondary", bg: "bg-surface ring-1 ring-inset ring-line", fill: "bg-line" },
};

export const ACTUAL_TONE: Tone = { text: "text-actual-fg", bg: "bg-actual-bg", fill: "bg-actual-fg" };
export const SIGNAL_TONE: Tone = { text: "text-signal-fg", bg: "bg-signal-bg", fill: "bg-ink-secondary" };

export function changeTone(t: string): Tone {
  return CHANGE_TONE[t as ChangeType] ?? CHANGE_TONE.largely_unchanged;
}

export function directionOf(t: string): Direction {
  return DIRECTION_OF[t as ChangeType] ?? "none";
}

/** Legacy field kept on the vocab entries; badges now take their colors from CHANGE_TONE. */
const CHANGE_TYPE_BADGE = "";

export const CHANGE_TYPE_VOCAB: Record<ChangeType, ChangeTypeVocab> = {
  new: {
    label: "New risk",
    helper: "Appears only in this year's filing.",
    marker: "+",
    badgeClass: CHANGE_TYPE_BADGE,
  },
  removed: {
    label: "Dropped risk",
    helper: "Appeared last year, not this year.",
    marker: "−",
    badgeClass: CHANGE_TYPE_BADGE,
  },
  expanded: {
    label: "Expanded",
    helper: "Substantially more language this year.",
    marker: "",
    badgeClass: CHANGE_TYPE_BADGE,
  },
  reduced: {
    label: "Scaled back",
    helper: "Substantially less language this year.",
    marker: "",
    badgeClass: CHANGE_TYPE_BADGE,
  },
  materially_reworded: {
    label: "Major update",
    helper: "Substantially rewritten from last year.",
    marker: "~",
    badgeClass: CHANGE_TYPE_BADGE,
  },
  largely_unchanged: {
    label: "Essentially unchanged",
    helper: "Little or no change in wording from last year.",
    marker: "=",
    badgeClass: CHANGE_TYPE_BADGE,
  },
};

export function changeTypeVocab(t: string): ChangeTypeVocab {
  return (
    CHANGE_TYPE_VOCAB[t as ChangeType] ?? {
      label: t.replace(/_/g, " "),
      helper: "",
      marker: "•",
      badgeClass: CHANGE_TYPE_BADGE,
    }
  );
}

/**
 * The title to show for a change. A `short_title` ending in an ellipsis is a deterministic
 * truncation fallback that says nothing on its own ("We are subject to complex laws, rules…"),
 * so the full heading is shown instead.
 */
export function displayTitle(shortTitle: string | null | undefined, fullTitle: string | null | undefined): string {
  const short = (shortTitle ?? "").trim();
  const full = (fullTitle ?? "").trim();
  if (!short) return shortTitleFromHeading(full);
  if (short.endsWith("…") || short.endsWith("...")) {
    // A truncation fallback: cut the full heading at a clause, or the truncation itself when the
    // full heading is not at hand (e.g. Trends rows), so "…laws, rules…" becomes "…laws".
    return shortTitleFromHeading(full || short.replace(/(…|\.\.\.)$/, ""));
  }
  return short;
}

/** "2 new risks", "1 major update", "3 expanded": a count with the change label. */
export function countedLabel(n: number, changeType: string): string {
  const label = changeTypeVocab(changeType).label.toLowerCase();
  const plural = n === 1 ? label : /\b(risk|update)$/.test(label) ? `${label}s` : label;
  return `${n} ${plural}`;
}

/** Clause boundaries where a legal heading can be cut without losing its subject. */
const CLAUSE_BREAKS = [", ", "; ", ": ", " which ", " that ", " may ", " might ", " could ", " including "];
const TRAILING_FUNCTION_WORDS = /\s+(and|or|the|of|to|a|an|our|its|their|in|on|for|with|by|as)$/i;
export const SHORT_TITLE_MAX_WORDS = 12;

/**
 * Deterministic display title from an official risk heading when no language-model short
 * title exists: the heading's first clause (cut at the earliest clause boundary that keeps at
 * least four words), trailing function words dropped, capped at SHORT_TITLE_MAX_WORDS words
 * with a visible ellipsis. "Failure to meet the evolving needs of our industry and markets may
 * adversely impact our financial results." -> "Failure to meet the evolving needs of our
 * industry and markets". The full heading is always shown on the detail page.
 */
export function shortTitleFromHeading(heading: string): string {
  const text = heading.trim().replace(/\s+/g, " ").replace(/[.;:]+$/, "");
  if (!text) return "";
  // Every clause boundary, in text order; the first one that leaves a clean head wins.
  const cuts: number[] = [];
  for (const brk of CLAUSE_BREAKS) {
    let from = 0;
    for (;;) {
      const i = text.indexOf(brk, from);
      if (i < 0) break;
      cuts.push(i);
      from = i + brk.length;
    }
  }
  cuts.sort((a, b) => a - b);
  let head = text;
  for (const i of cuts) {
    const candidate = text.slice(0, i).trim();
    if (candidate.split(" ").length < 4) continue;
    if (TRAILING_FUNCTION_WORDS.test(candidate)) continue; // "...have caused and" is not a title
    head = candidate;
    break;
  }
  head = head.replace(TRAILING_FUNCTION_WORDS, "").trim();
  const words = head.split(" ");
  if (words.length > SHORT_TITLE_MAX_WORDS) return words.slice(0, SHORT_TITLE_MAX_WORDS).join(" ").replace(TRAILING_FUNCTION_WORDS, "") + "…";
  return head;
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

export const HIGHLIGHT_TONE: Record<Highlight["kind"], Tone> = {
  potential_became_actual: ACTUAL_TONE,
  new_figure: SIGNAL_TONE,
  new_named_party: SIGNAL_TONE,
  new_risk: CHANGE_TONE.new,
  removed_risk: CHANGE_TONE.removed,
};

export function highlightTone(kind: string): Tone {
  return HIGHLIGHT_TONE[kind as Highlight["kind"]] ?? SIGNAL_TONE;
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
// Wording change level (the 0–100 score in words)
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
  label: "Wording change level",
  /** Visible prefix on every level meter, so "High" never reads as a risk rating. */
  prefix: "Wording change",
  helper: "How much the language changed, not how risky the company is.",
  /** One-line note at the top of the "All changes" table. */
  tableNote: `Wording change is High from ${LEVEL_HIGH_MIN}, Medium from ${LEVEL_MEDIUM_MIN}, else Low, on a 0 to 100 scale of how much the wording changed. It measures wording, not risk.`,
} as const;

/** The named party or figure a highlight is about; a hedge pair is explained by its quotes. */
export function factDetail(h: { kind: string; detail?: string | null }): string | null {
  if (h.kind === "new_named_party" || h.kind === "new_figure") return h.detail ?? null;
  return null;
}

/** Filled segments of the 3-segment level meter. */
export function levelSegments(score: number): 1 | 2 | 3 {
  const level = changeLevel(score);
  return level === "High" ? 3 : level === "Medium" ? 2 : 1;
}

/** The one-line color legend shown once near the top of a company page. */
export const LEGEND = {
  more: "more disclosure language",
  less: "less disclosure language",
  rewrite: "rewritten both ways",
  actual: "potential became actual",
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
