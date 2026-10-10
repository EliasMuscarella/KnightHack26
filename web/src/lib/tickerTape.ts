/**
 * Market-price ticker tape on the home page: payload validation and display formatting.
 * Pure functions (no React, no fetch) so they run in the browser, on the server and in
 * `node --test`. The payload comes from our own API (GET /ticker-tape), which caches delayed
 * quotes from Finnhub; it is still treated as untrusted input and checked field by field.
 *
 * Direction colors follow DESIGN.md's value-neutral families (blue up, orange down), never
 * green/red, and the sign and arrow always carry the direction too.
 */

export type TapeStatus = "ok" | "stale" | "unavailable";

export interface TapeQuote {
  symbol: string;
  name: string;
  price: number;
  change: number | null;
  change_pct: number | null;
  updated_at: string | null;
}

export interface TickerTapePayload {
  status: TapeStatus;
  source: string;
  as_of: string | null;
  quotes: TapeQuote[];
}

export type TapeDirection = "up" | "down" | "flat";

const SYMBOL = /^[A-Z.\-]{1,6}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const MAX_QUOTES = 120;

export const UNAVAILABLE_TAPE: TickerTapePayload = { status: "unavailable", source: "Finnhub", as_of: null, quotes: [] };

function finite(x: unknown): number | null {
  return typeof x === "number" && Number.isFinite(x) ? x : null;
}

function isoTime(x: unknown): string | null {
  if (typeof x !== "string" || x.length > 40 || !ISO.test(x)) return null;
  return Number.isNaN(Date.parse(x)) ? null : x;
}

function quote(x: unknown): TapeQuote | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  const symbol = typeof r.symbol === "string" ? r.symbol : "";
  if (!SYMBOL.test(symbol)) return null;
  const price = finite(r.price);
  if (price === null || price <= 0) return null;
  // A present-but-malformed change field marks the whole quote as malformed.
  if (r.change !== null && r.change !== undefined && finite(r.change) === null) return null;
  if (r.change_pct !== null && r.change_pct !== undefined && finite(r.change_pct) === null) return null;
  const name = typeof r.name === "string" && r.name.trim() && r.name.length <= 120 ? r.name.trim() : symbol;
  return {
    symbol,
    name,
    price,
    change: finite(r.change),
    change_pct: finite(r.change_pct),
    updated_at: isoTime(r.updated_at),
  };
}

/** Validates a /ticker-tape body; malformed quotes are dropped. Null when the body itself is unusable. */
export function parseTickerTape(body: unknown): TickerTapePayload | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (b.status !== "ok" && b.status !== "stale" && b.status !== "unavailable") return null;
  const quotes: TapeQuote[] = [];
  const seen = new Set<string>();
  if (Array.isArray(b.quotes)) {
    for (const raw of b.quotes) {
      const q = quote(raw);
      if (!q || seen.has(q.symbol)) continue;
      seen.add(q.symbol);
      quotes.push(q);
      if (quotes.length >= MAX_QUOTES) break;
    }
  }
  const source = typeof b.source === "string" && /^[A-Za-z0-9 .\-]{1,40}$/.test(b.source) ? b.source : "Finnhub";
  return { status: b.status, source, as_of: isoTime(b.as_of), quotes };
}

/** True when the tape has something to show; otherwise the home page renders exactly as without it. */
export function tapeVisible(p: TickerTapePayload | null | undefined): p is TickerTapePayload {
  return !!p && p.status !== "unavailable" && p.quotes.length > 0;
}

/** Direction from the day change (percent as a fallback); anything that rounds to 0.00 is flat. */
export function tapeDirection(q: Pick<TapeQuote, "change" | "change_pct">): TapeDirection {
  const v = q.change ?? q.change_pct;
  if (v === null || Math.round(v * 100) === 0) return "flat";
  return v > 0 ? "up" : "down";
}

const TWO = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MINUS = "−";

export function formatTapePrice(price: number): string {
  return TWO.format(price);
}

/** "+1.05", "−1.05", "0.00": the sign follows the direction, so a flat quote never reads "-0.00". */
function signed(v: number, dir: TapeDirection): string {
  const abs = TWO.format(Math.abs(v));
  if (dir === "up") return `+${abs}`;
  if (dir === "down") return `${MINUS}${abs}`;
  return TWO.format(0);
}

/** "+1.05 (+0.58%)"; null when the quote carries no change at all. */
export function formatTapeChange(q: Pick<TapeQuote, "change" | "change_pct">): string | null {
  const dir = tapeDirection(q);
  const pct = q.change_pct === null ? null : `${signed(q.change_pct, tapeDirection({ change: null, change_pct: q.change_pct }))}%`;
  if (q.change === null) return pct;
  const abs = signed(q.change, dir);
  return pct === null ? abs : `${abs} (${pct})`;
}

const ET = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/**
 * "4:02 PM ET" or, with the date, "Oct 9, 4:02 PM ET". Built from formatToParts with plain
 * spaces in a fixed time zone, so server and browser render the same string (no hydration mismatch).
 */
export function formatTapeTime(iso: string | null, withDate = false): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const parts: Record<string, string> = {};
  for (const p of ET.formatToParts(new Date(t))) parts[p.type] = p.value;
  const time = `${parts.hour}:${parts.minute} ${(parts.dayPeriod ?? "").toUpperCase()} ET`;
  return withDate ? `${parts.month} ${parts.day}, ${time}` : time;
}

/** Animation length for one pass of the list: about 2.5 seconds per quote, so symbols stay readable. */
export function tapeDurationSeconds(count: number): number {
  return Math.max(20, Math.round(count * 2.5));
}
