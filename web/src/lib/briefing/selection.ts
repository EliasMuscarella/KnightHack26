/**
 * Briefing selection parsed from URL search params. Strict on purpose: tickers must match the
 * ticker pattern (client and server), the count is capped, and free text is trimmed and length
 * limited. Nothing here touches the network or the filesystem.
 */
import { TICKER_PATTERN } from "@/lib/ticker";

import { MAX_BRIEFING_COMPANIES } from "./types";

export const MAX_TITLE_CHARS = 80;
export const MAX_PREPARED_FOR_CHARS = 80;
export const DEFAULT_TITLE = "Disclosure Briefing";

export interface BriefingSelection {
  /** Uppercase, validated, de-duplicated, in the order given, at most MAX_BRIEFING_COMPANIES. */
  tickers: string[];
  /** Tickers that failed validation (for an error message), never echoed raw into HTML. */
  rejected: string[];
  /** True when more than the cap were given; the extra ones are dropped. */
  truncated: boolean;
  title: string;
  preparedFor: string | null;
}

type ParamValue = string | string[] | undefined;

function first(v: ParamValue): string {
  return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
}

/** Collapse whitespace, strip control characters, cap the length. Rendered as text only. */
export function cleanText(v: ParamValue, max: number): string {
  const s = first(v)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return s.length > max ? s.slice(0, max).trimEnd() : s;
}

/** "nvda, amd,MSFT" -> ["NVDA", "AMD", "MSFT"]; invalid entries are listed in `rejected`. */
export function parseTickers(v: ParamValue): Pick<BriefingSelection, "tickers" | "rejected" | "truncated"> {
  const raw = (Array.isArray(v) ? v : [v ?? ""]).flatMap((s) => s.split(/[,\s]+/));
  const tickers: string[] = [];
  const rejected: string[] = [];
  for (const piece of raw) {
    const t = piece.trim().toUpperCase();
    if (!t) continue;
    if (!TICKER_PATTERN.test(t)) {
      if (rejected.length < 5) rejected.push(t.slice(0, 12));
      continue;
    }
    if (!tickers.includes(t)) tickers.push(t);
  }
  const truncated = tickers.length > MAX_BRIEFING_COMPANIES;
  return { tickers: truncated ? tickers.slice(0, MAX_BRIEFING_COMPANIES) : tickers, rejected, truncated };
}

export function parseSelection(params: Record<string, ParamValue> | undefined | null): BriefingSelection {
  const p = params ?? {};
  const { tickers, rejected, truncated } = parseTickers(p.tickers);
  const title = cleanText(p.title, MAX_TITLE_CHARS) || DEFAULT_TITLE;
  const preparedFor = cleanText(p.for, MAX_PREPARED_FOR_CHARS) || null;
  return { tickers, rejected, truncated, title, preparedFor };
}

/** Query string for a selection, rebuilt from validated values only (never from raw input). */
export function selectionQuery(sel: Pick<BriefingSelection, "tickers" | "title" | "preparedFor">): string {
  const q = new URLSearchParams();
  q.set("tickers", sel.tickers.join(","));
  if (sel.title && sel.title !== DEFAULT_TITLE) q.set("title", sel.title);
  if (sel.preparedFor) q.set("for", sel.preparedFor);
  return q.toString();
}
