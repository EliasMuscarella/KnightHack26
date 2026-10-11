/**
 * Disclosure Briefing model: everything the briefing document renders, for one or more companies.
 *
 * Built by `build.ts` from published comparisons plus the trends payload; rendered by
 * `components/briefing/BriefingDocument.tsx`; printed to PDF by `app/api/briefing.pdf`.
 *
 * Rules the model must satisfy (RiskDiff invariants):
 * - Every quote is a verbatim filing sentence looked up by sentence id; nothing is paraphrased.
 * - Every number comes from the reports or the trends payload; nothing is estimated or invented.
 * - Interpretive text appears only as `supportSource: "validated_claim"` (an LLM claim that passed
 *   the citation validator at publish time) or as neutral text built from data. No risk ratings,
 *   no probability language, no advice, no "riskier".
 * - Same analysis ids + same template version => the same briefing (except `generatedAt`).
 */
import type { ChangeType, DiffSpan, Highlight } from "@/types/comparison";

export type HighlightKind = Highlight["kind"];

/** Bump when the briefing's content rules change (what is included, ranked or worded). */
export const BRIEFING_TEMPLATE_VERSION = "1.0.0";

/**
 * Upper bound on companies in one briefing: bounds the render and keeps the PDF a document rather than
 * a dump. Raised from 12 to 20 once the library passed 12, so a whole-library briefing stays possible;
 * the evidence pages grow by about one page per company.
 */
export const MAX_BRIEFING_COMPANIES = 20;

export interface BriefingCompany {
  ticker: string;
  /** Display name from names.ts (e.g. "NVIDIA"). */
  name: string;
  /** Official SEC name (e.g. "NVIDIA CORP"), used in the audit trail and citations. */
  officialName: string;
  analysisId: string;
  oldFiscalYear: number;
  newFiscalYear: number;
  /** YYYY-MM-DD period ends, for the fiscal-year note. */
  oldPeriodEnd: string;
  newPeriodEnd: string;
  /** YYYY-MM-DD. */
  newFilingDate: string;
  newAccession: string;
  oldAccession: string;
  newEdgarUrl: string;
  oldEdgarUrl: string;
  isFixture: boolean;
  totalRiskFactors: number;
  meaningfulChanges: number;
  byChangeType: Record<ChangeType, number>;
  newCount: number;
  droppedCount: number;
  wordsThisYear: number;
  wordsLastYear: number;
  interpretationStatus: string;
}

/** A verbatim sentence with the analyst's marks (insert on the new side, delete on the old side). */
export interface MarkedQuote {
  sentenceId: string | null;
  text: string;
  spans: DiffSpan[] | null;
}

export interface HeadlineStats {
  wordsThisYear: number;
  /** wordsThisYear / 250 words per minute / 60, rounded to one decimal. */
  readingHours: number;
  changed: number;
  totalRiskFactors: number;
  unchanged: number;
  newCount: number;
  droppedCount: number;
  /** Figures that were not in last year's filing (kind "new_figure" highlights), largest first. */
  newFigures: { count: number; examples: string[] };
}

export type ReadFirstKind = "potential_became_actual" | "new_figure" | "spreading" | "quiet" | "new_risk" | "removed_risk";

export interface ReadFirstItem {
  kind: ReadFirstKind;
  /** Bold lead built only from data: company name(s) plus the risk factor short title or the topic. */
  lead: string;
  /** One supporting sentence, or null. */
  support: string | null;
  /** Where `support` came from. "validated_claim" = an LLM claim that passed the citation validator. */
  supportSource: "validated_claim" | "data" | null;
  tickers: string[];
  changeId: string | null;
  /** The page of the briefing that carries the evidence. */
  pageRef: 2 | 3 | null;
}

export interface CoverageRow {
  ticker: string;
  name: string;
  /** e.g. "FY2024 → FY2025" (data, as in the example briefing). */
  fyLabel: string;
  changed: number;
  total: number;
  mix: Record<ChangeType, number>;
  newCount: number;
  droppedCount: number;
  wordsThisYear: number;
  /** wordsThisYear - wordsLastYear. */
  wordsDelta: number;
}

export interface ThemeQuote {
  ticker: string;
  name: string;
  changeId: string;
  shortTitle: string;
  changeType: ChangeType | null;
  quote: MarkedQuote;
  edgarUrl: string;
  isFixture: boolean;
}

export interface Theme {
  /** Topic key from the trends payload. */
  topic: string;
  /** Sentence-case label for display. */
  label: string;
  companyCount: number;
  sentenceCount: number;
  tickers: string[];
  /** One quote per company, at most four. */
  quotes: ThemeQuote[];
  /** Companies with a hit but no quote shown ("Also new this year: …"), as display names. */
  alsoNamed: string[];
}

export interface TopicMatrix {
  topics: { topic: string; label: string; companyCount: number }[];
  rows: { ticker: string; name: string; hits: boolean[] }[];
}

export interface BeforeAfterQuote {
  ticker: string;
  name: string;
  changeId: string;
  shortTitle: string;
  kind: HighlightKind;
  /** The deterministic signal value behind it (e.g. "$4.5 billion", "may -> experienced"). */
  detail: string | null;
  /** True when a figure changed rather than appeared (both sides present for a "new_figure"). */
  figureChanged: boolean;
  old: MarkedQuote | null;
  new: MarkedQuote | null;
  oldEdgarUrl: string;
  newEdgarUrl: string;
  isFixture: boolean;
}

export interface RiskListItem {
  ticker: string;
  name: string;
  changeId: string;
  /** Full heading as filed. */
  title: string;
  shortTitle: string;
  changeType: ChangeType;
  /** Deterministic note (e.g. "names Groq"), or null. */
  note: string | null;
}

export interface QuietCompany {
  ticker: string;
  name: string;
  changed: number;
  total: number;
  /** Its meaningful changes, for completeness; empty when changed === 0. */
  items: RiskListItem[];
}

export interface ManagementQuestion {
  ticker: string;
  name: string;
  changeId: string;
  riskFactorTitle: string;
  /** e.g. "new", "dropped", "potential became actual", "new figure". */
  basis: string;
  /** Templated from the change type and anchored to the risk factor; never asserts an unverified fact. */
  question: string;
}

export interface AuditRow {
  ticker: string;
  name: string;
  fyLabel: string;
  /** YYYY-MM-DD of the latest 10-K. */
  latestFiled: string;
  accession: string;
  edgarUrl: string;
  analysisId: string;
  isFixture: boolean;
}

export interface BriefingModel {
  templateVersion: string;
  /** sha256 over the sorted analysis ids and the template version; identical for identical inputs. */
  briefingId: string;
  /** ISO-8601 UTC. The only field that differs between two runs on the same inputs. */
  generatedAt: string;
  /** From the trends payload's computed_at, else null. */
  libraryAsOf: string | null;
  /** User-supplied or default title, already sanitized (see selection.ts). */
  title: string;
  /** Optional "Prepared for" line, user-supplied and sanitized. */
  preparedFor: string | null;
  companies: BriefingCompany[];
  headline: HeadlineStats;
  readFirst: ReadFirstItem[];
  coverage: CoverageRow[];
  /** Shared topics among the selected companies (>= 2 companies, or >= 1 for a single company). */
  themes: Theme[];
  /** Null when fewer than two companies or no topics. */
  matrix: TopicMatrix | null;
  actuals: BeforeAfterQuote[];
  figures: BeforeAfterQuote[];
  newRisks: RiskListItem[];
  newRisksOmitted: number;
  droppedRisks: RiskListItem[];
  droppedRisksOmitted: number;
  quiet: QuietCompany[];
  questions: ManagementQuestion[];
  audit: AuditRow[];
  /** e.g. "Fiscal years differ by company: NVIDIA's FY2026 ended in January 2026, …", or null. */
  fiscalYearNote: string | null;
  /** Caveats to print verbatim (sections omitted, keyword matching, fixture data, …). */
  notes: string[];
  hasFixture: boolean;
  /** Companies requested but not found in the library (tickers, uppercase). */
  missingTickers: string[];
}
