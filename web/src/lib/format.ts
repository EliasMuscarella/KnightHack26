import type { Category, ChangeType, FilingSide } from "@/types/comparison";

export interface ChangeTypeMeta {
  label: string;
  /** Text marker shown next to the label so meaning never depends on color alone. */
  marker: string;
  /** Tailwind classes for the badge (background, text, border). */
  badgeClass: string;
  description: string;
}

export const CHANGE_TYPE_ORDER: ChangeType[] = [
  "new",
  "expanded",
  "materially_reworded",
  "reduced",
  "removed",
  "largely_unchanged",
];

export const CHANGE_TYPE_META: Record<ChangeType, ChangeTypeMeta> = {
  new: {
    label: "New",
    marker: "+",
    badgeClass: "bg-add-bg text-add-fg border-add-line",
    description: "Risk factor appears only in the newer filing.",
  },
  removed: {
    label: "Removed",
    marker: "−",
    badgeClass: "bg-del-bg text-del-fg border-del-line",
    description: "Risk factor appears only in the older filing.",
  },
  expanded: {
    label: "Expanded",
    marker: "↗",
    badgeClass: "bg-exp-bg text-exp-fg border-exp-line",
    description: "Matched risk factor with substantially more text in the newer filing.",
  },
  reduced: {
    label: "Reduced",
    marker: "↘",
    badgeClass: "bg-red-bg text-red-fg border-red-line",
    description: "Matched risk factor with substantially less text in the newer filing.",
  },
  materially_reworded: {
    label: "Reworded",
    marker: "~",
    badgeClass: "bg-mod-bg text-mod-fg border-mod-line",
    description: "Matched risk factor whose wording changed materially.",
  },
  largely_unchanged: {
    label: "Largely unchanged",
    marker: "=",
    badgeClass: "bg-neutral-bg text-ink-muted border-line-strong",
    description: "Matched risk factor with little or no wording change.",
  },
};

export function changeTypeMeta(t: string): ChangeTypeMeta {
  return (
    CHANGE_TYPE_META[t as ChangeType] ?? {
      label: t,
      marker: "•",
      badgeClass: "bg-neutral-bg text-ink-muted border-line-strong",
      description: "",
    }
  );
}

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
