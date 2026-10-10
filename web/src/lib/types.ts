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
  top_highlight?: { kind: string; short_title: string; title?: string; figure_changed?: boolean; detail?: string | null } | null;
  /** Optional shared-library metadata from GET /companies (absent on plain local reports). */
  analysis_id?: string;
  published_by?: string | null;
  /** ISO-8601 UTC timestamp. */
  published_at?: string | null;
  /** Where the API found the report ("local" files or the "remote" shared library). */
  library_source?: "local" | "remote";
}

/** GET /store/health: remote state; "unknown" when the API is down, slow, or lacks the endpoint. */
export type LibraryStatus = "ok" | "connecting" | "offline" | "disabled" | "unknown";

/** Shared-store state as the trends endpoint reports it. */
export type StoreState = "ok" | "connecting" | "disabled" | "offline";

export interface TrendsCompany {
  ticker: string;
  name: string;
  analysis_id: string;
  old_fiscal_year: number;
  new_fiscal_year: number;
  total_changes: number;
  meaningful_changes: number;
  by_change_type: Record<string, number>;
  cik?: string | null;
  old_accession?: string | null;
  new_accession?: string | null;
  edgar_url_old?: string | null;
  edgar_url_new?: string | null;
}

export interface TrendsTopicExample {
  ticker: string;
  change_id: string;
  sentence_id: string;
  short_title: string;
  status: "added" | "modified";
  text: string;
  /** Character offsets inside `text` of the words the deterministic diff marked as new. */
  added_spans: [number, number][];
  matched_terms: string[];
}

export interface TrendsTopic {
  topic: string;
  source: "lexicon" | "entity" | "phrase";
  company_count: number;
  sentence_count: number;
  companies: string[];
  examples: TrendsTopicExample[];
}

export interface TrendsCategoryActivity {
  ticker: string;
  category: string;
  risk_factors: number;
  change_ids: string[];
  added_sentences: number;
  removed_sentences: number;
  modified_sentences: number;
  added_words: number;
  removed_words: number;
  modified_words: number;
  max_score: number;
}

export interface TrendsActual {
  ticker: string;
  company_name: string;
  change_id: string;
  short_title: string;
  old_sentence_id: string | null;
  new_sentence_id: string | null;
  old_text: string | null;
  new_text: string | null;
  score: number;
  old_spans: [number, number][];
  new_spans: [number, number][];
}

/** GET /trends payload (validated in api.ts before use). */
export interface TrendsPayload {
  status: StoreState;
  source: "databricks" | "local" | null;
  computed_at: string | null;
  companies: TrendsCompany[];
  headline: { companies: number; meaningful_changes: number; top_topic: { topic: string; company_count: number } | null };
  topics: TrendsTopic[];
  category_activity: TrendsCategoryActivity[];
  potential_to_actual: TrendsActual[];
  change_mix: { ticker: string; by_change_type: Record<string, number> }[];
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
