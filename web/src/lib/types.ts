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
