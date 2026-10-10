/**
 * Pure helpers for the Trends page: ranking, the heatmap matrix and the source line. No fetching,
 * no React, unit-tested with node --test. Every number counts disclosure wording changes.
 */
import type { TrendsCategoryActivity, TrendsCompany, TrendsPayload, TrendsTopic } from "@/lib/types";

export const MIN_SHARED_COMPANIES = 2;
export const TOP_TOPICS = 10;
export const MAX_HEATMAP_COLUMNS = 10;
export const OTHER_CATEGORY = "other";

/** Topics newly added by at least MIN_SHARED_COMPANIES companies, ranked; then the rest. */
export function rankTopics(topics: TrendsTopic[]): { shared: TrendsTopic[]; single: TrendsTopic[] } {
  const byRank = (a: TrendsTopic, b: TrendsTopic) => b.company_count - a.company_count || b.sentence_count - a.sentence_count || a.topic.localeCompare(b.topic);
  const sorted = [...topics].sort(byRank);
  return {
    shared: sorted.filter((t) => t.company_count >= MIN_SHARED_COMPANIES && t.examples.length > 0),
    single: sorted.filter((t) => t.company_count < MIN_SHARED_COMPANIES && t.examples.length > 0 && t.source !== "phrase"),
  };
}

export interface HeatCell {
  ticker: string;
  category: string;
  risk_factors: number;
  added: number;
  removed: number;
  modified: number;
  /** Net words: positive = more language added than removed. */
  net_words: number;
  /** Words added plus words removed (the base for the direction share). */
  turnover: number;
  /** Sentences touched (added + removed + modified). */
  activity: number;
}

export interface Heatmap {
  columns: string[];
  rows: { ticker: string; total: number; cells: Map<string, HeatCell> }[];
  maxActivity: number;
  maxNet: number;
}

/** Companies (rows, by total activity) by categories (at most MAX_HEATMAP_COLUMNS, rest as Other). */
export function buildHeatmap(activity: TrendsCategoryActivity[], companies: TrendsCompany[]): Heatmap {
  const byCategory = new Map<string, number>();
  for (const a of activity) {
    byCategory.set(a.category, (byCategory.get(a.category) ?? 0) + a.added_sentences + a.removed_sentences + a.modified_sentences);
  }
  const ranked = [...byCategory.entries()].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0])).map(([c]) => c);
  const keep = ranked.slice(0, MAX_HEATMAP_COLUMNS);
  const columns = ranked.length > MAX_HEATMAP_COLUMNS ? [...keep, OTHER_CATEGORY] : keep;
  const colOf = (c: string) => (keep.includes(c) ? c : OTHER_CATEGORY);

  const rowMap = new Map<string, Map<string, HeatCell>>();
  for (const a of activity) {
    const col = colOf(a.category);
    const row = rowMap.get(a.ticker) ?? new Map<string, HeatCell>();
    const cell = row.get(col) ?? { ticker: a.ticker, category: col, risk_factors: 0, added: 0, removed: 0, modified: 0, net_words: 0, turnover: 0, activity: 0 };
    cell.risk_factors += a.risk_factors;
    cell.added += a.added_sentences;
    cell.removed += a.removed_sentences;
    cell.modified += a.modified_sentences;
    cell.net_words += a.added_words - a.removed_words;
    cell.turnover += a.added_words + a.removed_words;
    cell.activity += a.added_sentences + a.removed_sentences + a.modified_sentences;
    row.set(col, cell);
    rowMap.set(a.ticker, row);
  }
  const tickers = new Set([...companies.map((c) => c.ticker), ...rowMap.keys()]);
  const rows = [...tickers]
    .map((ticker) => {
      const cells = rowMap.get(ticker) ?? new Map<string, HeatCell>();
      const total = [...cells.values()].reduce((s, c) => s + c.activity, 0);
      return { ticker, total, cells };
    })
    .sort((a, b) => b.total - a.total || a.ticker.localeCompare(b.ticker));
  let maxActivity = 0;
  let maxNet = 0;
  for (const r of rows) for (const c of r.cells.values()) {
    maxActivity = Math.max(maxActivity, c.activity);
    maxNet = Math.max(maxNet, Math.abs(c.net_words));
  }
  return { columns, rows, maxActivity, maxNet };
}

export type CellTone = "more" | "less" | "rewrite" | "empty";

/** A cell counts as directional when the net word change is at least this share of word turnover. */
export const DIRECTION_SHARE = 0.2;

/** Direction of a cell: blue when more words were added than removed, orange when fewer, ink when balanced. */
export function cellTone(cell: HeatCell | undefined): CellTone {
  if (!cell || cell.activity === 0) return "empty";
  const share = cell.turnover > 0 ? Math.abs(cell.net_words) / cell.turnover : 0;
  if (share >= DIRECTION_SHARE) return cell.net_words > 0 ? "more" : "less";
  return "rewrite";
}

/** 0.15 to 1 by activity relative to the busiest cell (never 0 for a non-empty cell). */
export function cellIntensity(cell: HeatCell | undefined, maxActivity: number): number {
  if (!cell || cell.activity === 0 || maxActivity === 0) return 0;
  return 0.15 + 0.85 * Math.min(1, cell.activity / maxActivity);
}

export function cellDescription(name: string, categoryLabel: string, cell: HeatCell): string {
  const rf = cell.risk_factors === 1 ? "1 risk factor" : `${cell.risk_factors} risk factors`;
  return `${name}, ${categoryLabel}: ${cell.added} sentences added, ${cell.removed} removed, ${cell.modified} modified across ${rf}.`;
}

/** "updated 2 min ago" style relative time; null when unknown. */
export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const s = Math.max(0, Math.round((now.getTime() - t) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} ${h === 1 ? "hour" : "hours"} ago`;
  const d = Math.round(h / 24);
  return `${d} days ago`;
}

export function sourceLine(p: Pick<TrendsPayload, "source" | "computed_at">, now?: Date): string {
  if (p.source === "databricks") {
    const rel = relativeTime(p.computed_at, now);
    return rel ? `Computed in Databricks, updated ${rel}` : "Computed in Databricks";
  }
  return "Computed from reports on this computer";
}

/** Order and labels of the change-mix segments (direction colors, meaningful types only). */
export const MIX_TYPES = ["new", "expanded", "materially_reworded", "reduced", "removed"] as const;

export function mixTotal(by: Record<string, number>): number {
  return MIX_TYPES.reduce((s, t) => s + (by[t] ?? 0), 0);
}
