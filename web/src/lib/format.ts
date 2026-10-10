import type { Category, FilingSide } from "@/types/comparison";

const CATEGORY_LABELS: Partial<Record<Category, string>> = {
  artificial_intelligence: "Artificial intelligence",
  supply_chain: "Supply chain",
  customer_concentration: "Customer concentration",
  interest_rates: "Interest rates",
  foreign_exchange: "Foreign exchange",
  intellectual_property: "Intellectual property",
};

export function categoryLabel(c: string): string {
  const known = CATEGORY_LABELS[c as Category];
  if (known) return known;
  const words = c.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Formats an ISO date (YYYY-MM-DD...) without timezone shifts (stable across server/client). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1];
  if (!month) return iso;
  return `${month} ${Number(m[3])}, ${m[1]}`;
}

export function sideLabel(side: FilingSide, oldFY: number, newFY: number): string {
  return side === "old" ? `FY${oldFY}` : `FY${newFY}`;
}

export function formatRatio(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return x.toFixed(digits);
}

export function formatShare(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${Math.round(x * 100)}%`;
}

/** Text-fragment component encoding: encodeURIComponent plus '-' and ',' (fragment syntax chars). */
function encodeFragmentPart(s: string): string {
  return encodeURIComponent(s).replace(/-/g, "%2D").replace(/,/g, "%2C");
}

/**
 * Deep link into the SEC document that asks the browser to scroll to and highlight the
 * sentence (URL text fragments, `#:~:text=start,end`). Short sentences use the whole text.
 * Browsers without text-fragment support simply open the document.
 */
export function textFragmentUrl(edgarUrl: string, sentence: string): string {
  const words = sentence.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  if (words.length === 0) return edgarUrl;
  const base = edgarUrl.split("#")[0];
  if (words.length <= 10) {
    return `${base}#:~:text=${encodeFragmentPart(words.join(" "))}`;
  }
  const start = words.slice(0, 6).join(" ");
  const end = words.slice(-4).join(" ");
  return `${base}#:~:text=${encodeFragmentPart(start)},${encodeFragmentPart(end)}`;
}

export function pluralize(n: number, one: string, many?: string): string {
  return `${n} ${n === 1 ? one : (many ?? one + "s")}`;
}
