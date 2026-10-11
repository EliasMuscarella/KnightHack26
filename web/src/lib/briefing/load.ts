/**
 * Server-side loader: comparisons for the selected tickers (published files, then the API) plus
 * the trends payload, handed to `buildBriefing`. Companies that are not in the library are
 * reported in `missingTickers`, never faked.
 */
import { getComparison, getTrends } from "@/lib/data";
import type { Comparison } from "@/types/comparison";

import { buildBriefing } from "./build";
import type { BriefingSelection } from "./selection";
import type { BriefingModel } from "./types";

export interface BriefingInput {
  comparisons: Comparison[];
  trends: import("@/lib/types").TrendsPayload | null;
  title: string;
  preparedFor: string | null;
  /** ISO-8601 UTC; injected so tests and the id stay deterministic. */
  generatedAt: string;
  /** Tickers requested but not found, in request order. */
  missingTickers: string[];
}

export async function loadBriefing(sel: BriefingSelection, now: Date = new Date()): Promise<BriefingModel | null> {
  if (sel.tickers.length === 0) return null;
  const [results, trends] = await Promise.all([
    Promise.all(sel.tickers.map((t) => getComparison(t))),
    getTrends().catch(() => null),
  ]);
  const comparisons: Comparison[] = [];
  const missingTickers: string[] = [];
  results.forEach((r, i) => {
    if (r) comparisons.push(r.comparison);
    else missingTickers.push(sel.tickers[i]);
  });
  if (comparisons.length === 0) return null;
  return buildBriefing({
    comparisons,
    trends,
    title: sel.title,
    preparedFor: sel.preparedFor,
    generatedAt: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
    missingTickers,
  });
}
