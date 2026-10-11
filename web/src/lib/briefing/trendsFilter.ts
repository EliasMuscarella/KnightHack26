/**
 * The trends payload restricted to a briefing's selection. The payload covers the whole library;
 * a briefing counts only the selected companies, so every topic is re-counted BEFORE ranking:
 * companies and examples outside the selection are dropped, `company_count` becomes the number of
 * distinct selected companies, and topics below the minimum are dropped (2 companies, or 1 when a
 * single company is selected). Category activity, potential-to-actual rows and the change mix get
 * the same ticker filter.
 *
 * `sentence_count`: the payload carries one example per company and a library-wide total, not a
 * per-company count. When every company of the topic is selected the library total is exact and
 * is kept; otherwise the count falls back to the examples kept (a lower bound), and the topic is
 * flagged `partialCount` so the caller can say so.
 */
import type { TrendsPayload, TrendsTopic } from "@/lib/types";

import { cmpDesc, cmpName } from "./order";

export interface FilteredTopic extends TrendsTopic {
  /** True when `sentence_count` is the examples kept rather than the library-wide total. */
  partialCount: boolean;
}

export interface FilteredTrends {
  topics: FilteredTopic[];
  category_activity: TrendsPayload["category_activity"];
  potential_to_actual: TrendsPayload["potential_to_actual"];
  change_mix: TrendsPayload["change_mix"];
  /** Selected tickers whose trends rows were computed from a different report (analysis id); excluded. */
  staleTickers: string[];
}

/** Minimum distinct selected companies for a topic to count as shared. */
export function minTopicCompanies(selectedCount: number): number {
  return selectedCount <= 1 ? 1 : 2;
}

/** Rank: company count desc, then sentence count desc, then name (the pipeline's order). */
export function compareTopics(a: Pick<TrendsTopic, "topic" | "company_count" | "sentence_count">, b: Pick<TrendsTopic, "topic" | "company_count" | "sentence_count">): number {
  return cmpDesc(a.company_count, b.company_count) || cmpDesc(a.sentence_count, b.sentence_count) || cmpName(a.topic, b.topic);
}

/**
 * Filter the payload to `selected` (ticker -> analysis id of the report in the briefing). A ticker
 * whose trends company row names a different analysis id is treated as not selected: its examples
 * would point at sentences that are not in the report being briefed.
 */
export function filterTrends(trends: TrendsPayload | null | undefined, selected: ReadonlyMap<string, string>): FilteredTrends {
  if (!trends) return { topics: [], category_activity: [], potential_to_actual: [], change_mix: [], staleTickers: [] };
  const trendsIds = new Map((trends.companies ?? []).map((c) => [c.ticker, c.analysis_id] as const));
  const staleTickers: string[] = [];
  const keep = new Set<string>();
  for (const [ticker, analysisId] of selected) {
    const tid = trendsIds.get(ticker);
    if (tid && analysisId && tid !== analysisId) staleTickers.push(ticker);
    else keep.add(ticker);
  }
  const min = minTopicCompanies(selected.size);
  const topics: FilteredTopic[] = [];
  for (const t of trends.topics ?? []) {
    const companies = [...new Set((t.companies ?? []).filter((x) => keep.has(x)))];
    if (companies.length < min) continue;
    const inTopic = new Set(companies);
    const examples = (t.examples ?? []).filter((e) => inTopic.has(e.ticker)).map((e) => ({ ...e, added_spans: e.added_spans.map(([a, b]) => [a, b] as [number, number]), matched_terms: [...e.matched_terms] }));
    const complete = companies.length === new Set(t.companies ?? []).size;
    topics.push({
      topic: t.topic,
      source: t.source,
      company_count: companies.length,
      sentence_count: complete ? t.sentence_count : examples.length,
      companies,
      examples,
      partialCount: !complete,
    });
  }
  topics.sort(compareTopics);
  return {
    topics,
    category_activity: (trends.category_activity ?? []).filter((r) => keep.has(r.ticker)),
    potential_to_actual: (trends.potential_to_actual ?? []).filter((r) => keep.has(r.ticker)),
    change_mix: (trends.change_mix ?? []).filter((r) => keep.has(r.ticker)),
    staleTickers: staleTickers.sort(),
  };
}

/** Lowercase words that are acronyms in a lemmatized phrase topic ("ai technology" -> "AI technology"). */
const ACRONYMS = new Set(["ai", "eu", "uk", "sec", "esg", "ftc", "doj", "irs", "gdpr", "oecd", "ip", "ceo", "gpu", "cpu"]);

/**
 * Sentence-case display label for a topic key. Lexicon and entity topics are already proper
 * labels ("Export controls", "AI regulation", "Brazil") and only get a capital first letter;
 * phrase topics are lowercase lemmas, so known acronyms are restored too. The Trends page shows
 * the raw key; this is the same text with the first letter capitalized.
 */
export function topicLabel(topic: string, source?: TrendsTopic["source"]): string {
  const t = topic.replace(/\s+/g, " ").trim();
  if (!t) return t;
  const words = source === "phrase" ? t.split(" ").map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w)) : t.split(" ");
  const s = words.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
