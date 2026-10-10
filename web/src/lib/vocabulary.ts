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
 * and a short title that is just the company name says nothing either: both fall back to
 * `shortTitleFromHeading` on the full heading (or on the short title itself when the heading is
 * not at hand, e.g. Trends rows). Callers that have the comparison pass `company.name`.
 */
export function displayTitle(
  shortTitle: string | null | undefined,
  fullTitle: string | null | undefined,
  companyName?: string | null,
): string {
  const short = (shortTitle ?? "").trim();
  const full = (fullTitle ?? "").trim();
  if (!short) return shortTitleFromHeading(full, companyName);
  const truncated = short.endsWith("…") || short.endsWith("...");
  if (truncated || isCompanyName(short, companyName)) {
    // Without the heading, the truncation itself is the source: it may stop mid-clause ("breach
    // of…"), so trailing dangling words are removed as in the first-words rule.
    const title = full ? shortTitleFromHeading(full, companyName) : cleanTruncation(short.replace(/(…|\.\.\.)$/, ""), companyName);
    // Only the company name and no heading to fall back on: no title (callers show their own label).
    return !full && isCompanyName(title, companyName) ? "" : title;
  }
  return short;
}

/** "2 new risks", "1 major update", "3 expanded": a count with the change label. */
export function countedLabel(n: number, changeType: string): string {
  const label = changeTypeVocab(changeType).label.toLowerCase();
  const plural = n === 1 ? label : /\b(risk|update)$/.test(label) ? `${label}s` : label;
  return `${n} ${plural}`;
}

// ---------------------------------------------------------------------------------------
// Short titles from official headings (the pipeline applies the same rule in Python)
// ---------------------------------------------------------------------------------------

export const SHORT_TITLE_MAX_WORDS = 10;
const SHORT_TITLE_MIN_WORDS = 4;

/** A clause boundary lies before a token that is one of these words. */
const BOUNDARY_BEFORE = new Set(
  "which that including because as if when where while whether due resulting and or but may might could would should will can".split(" "),
);

/** A title must not end on one of these words (it would stop mid-clause). */
const DANGLING = new Set(
  (
    "including include includes and or but of the a an to in on for with by as at from into which that our its their his her " +
    "we they it is are was were be been being may might could would should can will shall if when while because whether than " +
    "such other certain any all laws law inc corp co ltd plc llc"
  ).split(" "),
);

const CORPORATE_SUFFIX =
  /[\s,.]*\b(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|holdings|group|com)\b[.,\s]*$/i;
const TRAILING_PUNCT = /[,;:—–-]+$/;

/** Lowercase letters and digits only ("Alphabet Inc." -> "alphabetinc"). */
function nameKey(text: string): string {
  return text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

/** True when `text` is just the company name, with or without its corporate suffix. */
export function isCompanyName(text: string, companyName: string | null | undefined): boolean {
  if (!companyName) return false;
  const k = nameKey(text);
  if (!k) return false;
  return k === nameKey(companyName) || k === nameKey(companyName.replace(CORPORATE_SUFFIX, ""));
}

/** A token compared as a word: lowercase, surrounding punctuation removed. */
function bare(token: string): string {
  return token.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
}

/** Strips trailing , ; : — – - from the last token, dropping tokens that were only punctuation. */
function stripTrailingPunct(tokens: string[]): string[] {
  const out = [...tokens];
  while (out.length > 0) {
    const last = out[out.length - 1].replace(TRAILING_PUNCT, "");
    if (last) {
      out[out.length - 1] = last;
      break;
    }
    out.pop();
  }
  return out;
}

/** Removes trailing dangling words while at least SHORT_TITLE_MIN_WORDS words remain. */
const CONJUNCTIONS = new Set(["and", "or", "but"]);

/**
 * Drops trailing dangling words while at least the minimum number of words remains. When the
 * candidate was cut right before a conjunction and itself ends in "<conjunction> <word>", the
 * coordination continues past the cut ("…regulations, and political | and other actions"), so that
 * trailing pair goes too. Same rule as pipeline/highlights.py `_trim_candidate`.
 */
function dropDangling(tokens: string[], cutBeforeConjunction = false): string[] {
  let out = stripTrailingPunct(tokens);
  let pairRule = cutBeforeConjunction;
  for (;;) {
    if (out.length > SHORT_TITLE_MIN_WORDS && DANGLING.has(bare(out[out.length - 1]))) {
      out = stripTrailingPunct(out.slice(0, -1));
      continue;
    }
    if (pairRule && out.length >= SHORT_TITLE_MIN_WORDS + 2 && CONJUNCTIONS.has(bare(out[out.length - 2]))) {
      out = stripTrailingPunct(out.slice(0, -2));
      pairRule = false;
      continue;
    }
    break;
  }
  return out;
}

/** Step 4 of the rule: the first max words, cleaned at the end. */
function firstWords(tokens: string[]): string {
  return dropDangling(tokens.slice(0, SHORT_TITLE_MAX_WORDS)).join(" ");
}

/** A truncated short title without its heading: the clause rule, then trailing dangling words removed. */
function cleanTruncation(text: string, companyName?: string | null): string {
  const title = shortTitleFromHeading(text, companyName);
  return title ? dropDangling(title.split(" ")).join(" ") : "";
}

/**
 * Deterministic display title from an official risk heading (no language model, no ellipsis):
 *
 * 1. Collapse whitespace; strip surrounding quotes; strip trailing `.`, `;`, `:`.
 * 2. A heading of at most SHORT_TITLE_MAX_WORDS (10) words is returned as is.
 * 3. Clause boundaries lie after a token ending in `,` `;` `:` `—` `–` (or a lone ` - `) and
 *    before one of BOUNDARY_BEFORE ("which", "including", "and", "may", ...). For each boundary
 *    the candidate is the tokens before it, trailing punctuation stripped, trailing DANGLING words
 *    removed while at least 4 words remain. A candidate of 4..10 words whose last word is not
 *    DANGLING qualifies; the longest qualifying candidate wins.
 * 4. Otherwise: the first 10 words, cleaned the same way.
 * 5. A result that is just the company name is replaced by step 4.
 *
 * The full heading is always shown on the detail page.
 */
export function shortTitleFromHeading(heading: string | null | undefined, companyName?: string | null): string {
  const text = (heading ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ")
    .replace(/^["'“”‘’]+|["'“”‘’]+$/g, "")
    .trim()
    .replace(/[.;:]+$/, "")
    .trim();
  if (!text) return "";
  const tokens = text.split(" ");
  let result: string;
  if (tokens.length <= SHORT_TITLE_MAX_WORDS) {
    result = text;
  } else {
    let best: string[] | null = null;
    for (let i = 1; i < tokens.length; i++) {
      const prev = tokens[i - 1];
      const after = /[,;:—–]$/.test(prev) || prev === "-";
      const before = BOUNDARY_BEFORE.has(bare(tokens[i]));
      if (!after && !before) continue;
      const cand = dropDangling(tokens.slice(0, i), CONJUNCTIONS.has(bare(tokens[i] ?? "")));
      if (cand.length < SHORT_TITLE_MIN_WORDS || cand.length > SHORT_TITLE_MAX_WORDS) continue;
      if (DANGLING.has(bare(cand[cand.length - 1]))) continue;
      if (!best || cand.length > best.length) best = cand;
    }
    result = best ? best.join(" ") : firstWords(tokens);
  }
  if (isCompanyName(result, companyName)) result = firstWords(tokens);
  return result;
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
