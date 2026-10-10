/**
 * Frontend mirrors of API payloads that exist in pipeline/schema.py but are not emitted
 * into the generated src/types/comparison.ts (json2ts only emits types reachable from
 * `Comparison`). Keep these in sync with `CompanyCard` and `StageEvent` in schema.py.
 */

/** pipeline/schema.py: CompanyCard */
export interface CompanyCard {
  ticker: string;
  name: string;
  old_fiscal_year: number;
  new_fiscal_year: number;
  total_changes: number;
  by_change_type: Record<string, number>;
  file: string;
}

export type StageStatus = "started" | "done" | "cached" | "error";

/** pipeline/schema.py: StageEvent (one SSE `stage` event from POST /analyze). */
export interface StageEvent {
  stage: number;
  name: string;
  status: StageStatus;
  message?: string | null;
  ticker?: string | null;
}

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

/** Listing entry used by the home grid: CompanyCard plus fields read from the file. */
export interface CompanyListing extends CompanyCard {
  cik?: string;
  old_filing_date?: string;
  new_filing_date?: string;
  max_score?: number;
  is_fixture: boolean;
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
}
