/**
 * API payload types. `CompanyCard`, `StageEvent` and `StageStatus` come from the generated
 * contract (pipeline/schema.py → web/src/types/comparison.ts); the SSE envelope types below
 * describe the `complete` / `error` events of POST /analyze.
 */
import type { CompanyCard, StageEvent, StageStatus } from "@/types/comparison";

export type { CompanyCard, StageEvent, StageStatus };

/** SSE `complete` event payload. */
export interface AnalyzeComplete {
  ticker: string;
  analysis_id: string;
  file: string;
}

export type AnalyzeErrorCode =
  | "invalid_ticker"
  | "ticker_not_found"
  | "no_10k"
  | "extraction_failed"
  | "busy"
  | "timeout"
  | "sec_unavailable"
  | "internal";

/** SSE `error` event payload. */
export interface AnalyzeErrorEvent {
  code: AnalyzeErrorCode | string;
  message: string;
}

/** Listing entry used by the home grid: CompanyCard plus where it came from. */
export interface CompanyListing extends CompanyCard {
  source: "published" | "fixture" | "api";
  /**
   * The comparison's rank-1 highlight, computed server-side from the comparison file.
   * Absent for API cards (GET /companies does not carry highlights).
   */
  top_highlight?: { kind: string; short_title: string; title?: string; figure_changed?: boolean } | null;
  /** Optional shared-library metadata from GET /companies (absent on plain local reports). */
  analysis_id?: string;
  published_by?: string | null;
  /** ISO-8601 UTC timestamp. */
  published_at?: string | null;
  /** Where the API found the report ("local" files or the "remote" shared library). */
  library_source?: "local" | "remote";
}

/** GET /store/health → remote; "unknown" when the API is down, slow, or lacks the endpoint. */
export type LibraryStatus = "ok" | "offline" | "disabled" | "unknown";

/** GET /trends row: companies with at least one change of `change_type` in `category`. */
export interface TrendsCategoryRow {
  category: string;
  change_type: string;
  companies: number;
}

/** GET /trends row: number of highlights of `kind` in one company's report. */
export interface TrendsKindRow {
  ticker: string;
  company_name: string;
  kind: string;
  highlights: number;
}

/** GET /trends payload (validated in api.ts before use). */
export interface TrendsPayload {
  available: boolean;
  remote: Exclude<LibraryStatus, "unknown">;
  companies: number;
  by_category: TrendsCategoryRow[];
  by_kind: TrendsKindRow[];
}

/** contract/rubric.json (produced by the pipeline). */
export interface RubricFile {
  rubric_version: string;
  pipeline_version: string;
  questions: { id: string; text: string; points: number }[];
  weights: { signal: string; label: string; points: number; description: string }[];
  banned_phrases: string[];
  thresholds: Record<string, number>;
  /** Score caps (per-signal limits and the overall score cap). */
  caps: Record<string, number>;
}
