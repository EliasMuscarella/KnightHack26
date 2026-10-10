/**
 * Display trimming for verbatim filing quotes. The quote itself is never edited: a trimmed
 * quote is an exact prefix of the sentence followed by a visible ellipsis, and the full
 * sentence is always one click away.
 */

/** Sentences up to this many characters are shown in full. */
export const QUOTE_MAX_CHARS = 220;

const MAGNITUDE = /^(?:million|billion|trillion|thousand|percent|per|basis|%|x\b)/i;
const CURRENCY_PREFIX = /^(?:\$|US\$|€|£|¥|USD|EUR)$/i;

/** True when the text before `cut` has an unclosed double quotation mark. */
function insideQuote(text: string, cut: number): boolean {
  const head = text.slice(0, cut);
  const curlyOpen = (head.match(/“/g) ?? []).length;
  const curlyClose = (head.match(/”/g) ?? []).length;
  const straight = (head.match(/"/g) ?? []).length;
  return curlyOpen > curlyClose || straight % 2 === 1;
}

/** A cut at a space between `prev` and `next` would split a number from its unit or currency. */
function splitsNumber(prev: string, next: string): boolean {
  if (/\d[\d,.]*%?$/.test(prev) && MAGNITUDE.test(next)) return true;
  if (CURRENCY_PREFIX.test(prev) && /^\d/.test(next)) return true;
  if (/^(?:approximately|about|over|under|nearly|up)$/i.test(prev) && /^[$\d]/.test(next)) return true;
  return false;
}

function goodCut(text: string, i: number): boolean {
  // i is the index of a space character.
  const before = text.slice(0, i);
  const after = text.slice(i + 1);
  const prev = before.split(/\s+/).pop() ?? "";
  const next = after.split(/\s+/)[0] ?? "";
  if (!prev || !next) return false;
  if (insideQuote(text, i)) return false;
  if (splitsNumber(prev, next)) return false;
  return true;
}

export interface TrimmedQuote {
  /** The displayed prefix (without the ellipsis). Equal to the full text when not trimmed. */
  head: string;
  trimmed: boolean;
}

export function trimQuote(text: string, max = QUOTE_MAX_CHARS): TrimmedQuote {
  if (text.length <= max) return { head: text, trimmed: false };
  const spaces: number[] = [];
  for (let i = 0; i < text.length; i++) if (text[i] === " ") spaces.push(i);
  const within = spaces.filter((i) => i <= max && goodCut(text, i));
  // Prefer ending on a clause boundary (after , ; : or a dash) in the last 40% of the budget.
  const clause = within.filter((i) => i >= max * 0.6 && /[,;:—–]$/.test(text.slice(0, i)));
  let cut = clause.length ? clause[clause.length - 1] : within.length ? within[within.length - 1] : -1;
  if (cut < max * 0.5) {
    // Nothing usable in budget (e.g. a long quoted phrase): extend to the next good cut.
    const later = spaces.find((i) => i > max && i <= max + 120 && goodCut(text, i));
    if (later !== undefined) cut = later;
    else if (cut < 0) cut = spaces.filter((i) => i <= max).pop() ?? max;
  }
  if (cut >= text.length - 1) return { head: text, trimmed: false };
  const head = text.slice(0, cut).replace(/[\s,;:—–-]+$/, "");
  return { head, trimmed: true };
}
