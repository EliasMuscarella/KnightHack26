/* eslint-disable */
/** GENERATED from contract/comparison.schema.json by scripts/regen_contract.py. Do not edit. */

export type Category =
  | "geopolitical"
  | "supply_chain"
  | "regulation"
  | "cybersecurity"
  | "customer_concentration"
  | "competition"
  | "liquidity"
  | "credit"
  | "interest_rates"
  | "foreign_exchange"
  | "artificial_intelligence"
  | "intellectual_property"
  | "labor"
  | "climate"
  | "litigation"
  | "macroeconomic"
  | "other";
export type ChangeType = "new" | "removed" | "expanded" | "reduced" | "materially_reworded" | "largely_unchanged";
/**
 * ok = LLM ran and output validated; unavailable = no provider; skipped = not run for largely_unchanged; empty = ran but every claim was dropped.
 */
export type InterpretationStatus = "ok" | "unavailable" | "skipped" | "empty";
export type DiffOp = "equal" | "insert" | "delete";
export type FilingSide = "old" | "new";
export type SentenceStatus = "added" | "removed" | "modified" | "unchanged";
export type EmbeddingBackend = "sentence-transformers" | "lexical-fallback";
/**
 * 'ok' if the LLM stage ran for this comparison, else why not.
 */
export type InterpretationStatus1 = "ok" | "unavailable" | "skipped" | "empty";

export interface Comparison {
  analysis_id: string;
  /**
   * Ranked by score desc, then stable id.
   */
  changes: Change[];
  company: Company;
  /**
   * How the two filings were chosen (e.g. 'two most recent original 10-Ks; amendments excluded').
   */
  filing_selection_note: string;
  /**
   * True ONLY for the hand-made dev fixture. Published data must have False.
   */
  is_fixture?: boolean;
  model_ids: ModelIds;
  new_filing: FilingMeta;
  /**
   * Plain-language caveats, e.g. 'LLM stage unavailable: no provider configured'.
   */
  notes?: string[];
  old_filing: FilingMeta;
  pipeline_version: string;
  rubric_version: string;
  schema_version: string;
  sentence_index: {
    [k: string]: SentenceLocation;
  };
  summary: Summary;
  thresholds: Thresholds;
}
export interface Change {
  body_similarity?: number | null;
  categories: Category[];
  change_type: ChangeType;
  heading_similarity?: number | null;
  /**
   * Stable hash of (old_block_id, new_block_id).
   */
  id: string;
  interpretation: Interpretation;
  new_block_id?: string | null;
  /**
   * Full new block text (heading + body).
   */
  new_text?: string | null;
  new_title?: string | null;
  old_block_id?: string | null;
  /**
   * Full old block text (heading + body).
   */
  old_text?: string | null;
  old_title?: string | null;
  rank: number;
  score: number;
  score_breakdown: ScoreLine[];
  section_group?: string | null;
  sentences: Sentence[];
  signals: Signals;
  similarity?: number | null;
  stats: DiffStats;
  /**
   * Risk heading (new side if present, else old).
   */
  title: string;
}
export interface Interpretation {
  claims?: Claim[];
  dropped_claim_count?: number;
  dropped_reasons?: string[];
  model_id?: string | null;
  reason?: string | null;
  rubric?: RubricAnswer[];
  status: InterpretationStatus;
}
export interface Claim {
  cited_sentence_ids: string[];
  text: string;
}
export interface RubricAnswer {
  /**
   * After citation validation: a 'yes' without a valid citation becomes False.
   */
  answer: boolean;
  cited_sentence_ids?: string[];
  question: string;
  question_id: string;
  /**
   * Short LLM rationale (display only).
   */
  rationale?: string | null;
  /**
   * What the model said before validation (transparency).
   */
  raw_answer?: boolean | null;
}
export interface ScoreLine {
  /**
   * Must be non-empty whenever points != 0. Ids must exist in sentence_index.
   */
  cited_sentence_ids: string[];
  detail?: string | null;
  /**
   * Plain-English label shown in the UI.
   */
  label: string;
  points: number;
  /**
   * Machine key, e.g. 'hypothetical_to_actual', 'rubric_q1'.
   */
  signal: string;
}
export interface Sentence {
  /**
   * Similarity used to align the pair, if any.
   */
  alignment_similarity?: number | null;
  /**
   * For modified/unchanged: the aligned sentence id on the other side.
   */
  counterpart_id?: string | null;
  /**
   * Only for status == 'modified'.
   */
  diff_spans?: DiffSpan[] | null;
  id: string;
  /**
   * Display order in a unified (inline) view. Modified/unchanged pairs share the same pair_index (old entry first, then new).
   */
  pair_index: number;
  side: FilingSide;
  status: SentenceStatus;
  text: string;
}
/**
 * Word-level span inside a modified sentence. Old side carries equal/delete,
 * new side carries equal/insert. Concatenating `text` over a side's spans reproduces
 * that side's sentence text exactly.
 */
export interface DiffSpan {
  op: DiffOp;
  text: string;
}
export interface Signals {
  added_text_ratio: number;
  /**
   * Per-category similarity used to pick `categories`.
   */
  category_scores?: {
    [k: string]: number;
  };
  hypothetical_to_actual?: SignalHit[];
  new_entities?: SignalHit[];
  new_quantities?: SignalHit[];
  removed_text_ratio: number;
  /**
   * 1 - pair similarity (0 for new/removed).
   */
  semantic_shift: number;
}
/**
 * One concrete, cited detection by a deterministic signal.
 */
export interface SignalHit {
  /**
   * Plain-English explanation.
   */
  detail?: string | null;
  new_sentence_ids?: string[];
  old_sentence_ids?: string[];
  /**
   * What was detected, e.g. 'may -> has', 'Taiwan', '$1.2 billion'.
   */
  value: string;
}
export interface DiffStats {
  added: number;
  /**
   * Words in added sentences + inserted spans.
   */
  added_word_count: number;
  modified: number;
  new_sentence_count: number;
  new_word_count: number;
  old_sentence_count: number;
  old_word_count: number;
  removed: number;
  /**
   * Words in removed sentences + deleted spans.
   */
  removed_word_count: number;
  unchanged: number;
}
export interface Company {
  /**
   * 10-digit zero-padded CIK.
   */
  cik: string;
  name: string;
  ticker: string;
}
/**
 * Exact identifiers of every model/method that influenced the output.
 *
 * These feed `analysis_id`, so switching any of them yields a different id.
 */
export interface ModelIds {
  /**
   * How categories were assigned, e.g. 'embedding-similarity:BAAI/bge-m3'.
   */
  category_method: string;
  embedding_backend: EmbeddingBackend;
  /**
   * Hugging Face model id used for block embeddings, e.g. 'BAAI/bge-m3'. If the fallback lexical embedder was used this says so explicitly.
   */
  embedding_model: string;
  /**
   * Pinned LLM model id, if used.
   */
  llm_model?: string | null;
  /**
   * None when the LLM stage did not run.
   */
  llm_provider?: ("huggingface" | "gemini") | null;
  /**
   * NER model id, e.g. 'spacy/en_core_web_sm@3.8.0'.
   */
  ner_model: string;
  /**
   * sha256 of the exact prompt template text used for stage 7.
   */
  prompt_sha256?: string | null;
  /**
   * e.g. 'pysbd@0.3.4'.
   */
  sentence_splitter: string;
}
export interface FilingMeta {
  accession_number: string;
  block_count: number;
  /**
   * Filing index page on www.sec.gov.
   */
  edgar_index_url: string;
  /**
   * Direct URL of the primary document on www.sec.gov.
   */
  edgar_url: string;
  filing_date: string;
  fiscal_year: number;
  /**
   * '10-K' or '10-K/A'.
   */
  form: string;
  is_amendment?: boolean;
  item_1a_char_count: number;
  item_1a_word_count: number;
  period_of_report: string;
  primary_document: string;
  /**
   * Group headers found in Item 1A, e.g. 'Risks Related to Our Industry'.
   */
  section_groups?: string[];
}
export interface SentenceLocation {
  accession_number: string;
  block_id: string;
  char_end: number;
  /**
   * Offset into the extracted Item 1A plain text.
   */
  char_start: number;
  id: string;
  is_heading?: boolean;
  side: FilingSide;
  /**
   * Exact sentence text as extracted from the filing.
   */
  text: string;
}
export interface Summary {
  /**
   * Counts keyed by every Category (zeros included).
   */
  by_category: {
    [k: string]: number;
  };
  /**
   * Counts keyed by every ChangeType (zeros included).
   */
  by_change_type: {
    [k: string]: number;
  };
  interpretation_status: InterpretationStatus1;
  matched_pairs: number;
  max_score: number;
  new_block_count: number;
  old_block_count: number;
  total_changes: number;
}
/**
 * Matching + diff parameters in force for this run (transparency; recalibrated in eval).
 */
export interface Thresholds {
  body_weight: number;
  /**
   * added/removed ratio rules; see diff.classify_change_type.
   */
  expanded_ratio: number;
  heading_weight: number;
  /**
   * Min combined similarity to accept a match.
   */
  match_threshold: number;
  reworded_similarity: number;
  /**
   * Min similarity to align two sentences.
   */
  sentence_match_threshold: number;
  /**
   * At/above this an aligned pair is 'unchanged'.
   */
  sentence_unchanged_threshold: number;
}
