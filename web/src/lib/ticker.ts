/** Ticker validation shared by client and server (CLAUDE.md: `^[A-Z.\-]{1,6}$` after uppercasing). */
export const TICKER_PATTERN = /^[A-Z.\-]{1,6}$/;

/** Uppercase + trim, then validate. Returns null for anything that does not match. */
export function normalizeTicker(raw: string | null | undefined): string | null {
  if (typeof raw !== "string") return null;
  let value = raw.trim();
  try {
    value = decodeURIComponent(value);
  } catch {
    return null;
  }
  const upper = value.toUpperCase();
  return TICKER_PATTERN.test(upper) ? upper : null;
}

export const TICKER_HELP = "1 to 6 characters: letters, '.' or '-' (for example NVDA or BRK.B).";
