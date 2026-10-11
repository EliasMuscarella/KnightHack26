/**
 * The Disclosure Briefing model: a pure function of the selected published comparisons plus the
 * trends payload. No clock, no randomness, no I/O: the same input gives a deep-equal model
 * (`generatedAt` is injected by the caller).
 *
 * Every quote is looked up by sentence id in the comparison's `sentence_index` (lib/briefing/quotes.ts);
 * every count comes from the reports or the trends payload; the only interpretive sentences are
 * the first validated claim of a change (`supportSource: "validated_claim"`) or neutral sentences
 * built from data. Ranking rules are spelled out next to each section below.
 */
import { createHash } from "node:crypto";

import { displayName } from "@/lib/names";
import { displayTitle, isCompanyName, isFigureChanged } from "@/lib/vocabulary";
import type { Change, ChangeType, Comparison, Highlight } from "@/types/comparison";

import type { BriefingInput } from "./load";
import { cmpDesc, cmpFigure, cmpName, cmpStr } from "./order";
import { buildQuestions } from "./questions";
import { quoteById, spansFromOffsets } from "./quotes";
import { compareTopics, filterTrends, topicLabel, type FilteredTopic } from "./trendsFilter";
import {
  BRIEFING_TEMPLATE_VERSION,
  type AuditRow,
  type BeforeAfterQuote,
  type BriefingCompany,
  type BriefingModel,
  type CoverageRow,
  type HeadlineStats,
  type QuietCompany,
  type ReadFirstItem,
  type RiskListItem,
  type Theme,
  type ThemeQuote,
  type TopicMatrix,
} from "./types";

const CHANGE_TYPES: ChangeType[] = ["new", "removed", "expanded", "reduced", "materially_reworded", "largely_unchanged"];

/** Section caps (the printed layout's budget). */
export const LIMITS = {
  readFirstMax: 6,
  /** Fill with new (then dropped) risks only while fewer than this many items were found... */
  readFirstFillBelow: 4,
  /** ...and fill up to this many. */
  readFirstFillTo: 5,
  readFirstPerKind: 2,
  themes: 2,
  themeQuotes: 4,
  matrixTopics: 5,
  actuals: 6,
  figures: 6,
  riskList: 12,
  figureExamples: 2,
} as const;

/** Read-first "quiet" item: no meaningful change, or at most this share changed. */
export const READ_FIRST_QUIET_SHARE = 0.1;
/** Page 3 "quiet" list: no meaningful change, or at most this many AND at most this share. */
export const QUIET_MAX_CHANGES = 5;
export const QUIET_MAX_SHARE = 0.15;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function briefingId(analysisIds: string[], templateVersion = BRIEFING_TEMPLATE_VERSION): string {
  const h = createHash("sha256");
  h.update(JSON.stringify({ analysis_ids: [...analysisIds].sort(), template: templateVersion }));
  return h.digest("hex");
}

// ---------------------------------------------------------------------------------------
// Per-company context
// ---------------------------------------------------------------------------------------

interface Ctx {
  comp: Comparison;
  company: BriefingCompany;
  changes: Map<string, Change>;
}

interface HighlightRef {
  ctx: Ctx;
  h: Highlight;
  change: Change;
}

function companyOf(c: Comparison): BriefingCompany {
  const by = Object.fromEntries(CHANGE_TYPES.map((t) => [t, c.summary.by_change_type[t] ?? 0])) as Record<ChangeType, number>;
  return {
    ticker: c.company.ticker,
    name: displayName(c.company.name) || c.company.ticker,
    officialName: c.company.name,
    analysisId: c.analysis_id,
    oldFiscalYear: c.old_filing.fiscal_year,
    newFiscalYear: c.new_filing.fiscal_year,
    oldPeriodEnd: c.old_filing.period_of_report,
    newPeriodEnd: c.new_filing.period_of_report,
    newFilingDate: c.new_filing.filing_date,
    newAccession: c.new_filing.accession_number,
    oldAccession: c.old_filing.accession_number,
    newEdgarUrl: c.new_filing.edgar_url,
    oldEdgarUrl: c.old_filing.edgar_url,
    isFixture: c.is_fixture === true,
    totalRiskFactors: c.changes.length,
    meaningfulChanges: c.changes.length - by.largely_unchanged,
    byChangeType: by,
    newCount: by.new,
    droppedCount: by.removed,
    wordsThisYear: c.new_filing.item_1a_word_count,
    wordsLastYear: c.old_filing.item_1a_word_count,
    interpretationStatus: c.summary.interpretation_status,
  };
}

function fyLabel(c: BriefingCompany): string {
  return `FY${c.oldFiscalYear} → FY${c.newFiscalYear}`;
}

/** Shown when a risk factor's only heading is the company name (a page header the extractor kept). */
export const UNTITLED_RISK = "Risk factor without a separate heading";

/**
 * The change's short title for display (never a truncation or the bare company name). When the
 * filed heading is only the company name, the filed section group stands in ("Risks Related to
 * our Industry"), else a neutral label; nothing is paraphrased.
 */
function shortTitleOf(ctx: Ctx, change: Change): string {
  const companyName = ctx.comp.company.name;
  const t = displayTitle(change.short_title, change.title, companyName) || change.title;
  if (!isCompanyName(t, companyName)) return t;
  const group = (change.section_group ?? "").trim();
  return group && !isCompanyName(group, companyName) ? group : UNTITLED_RISK;
}

function highlightsOf(ctxs: Ctx[], kind: Highlight["kind"]): HighlightRef[] {
  const out: HighlightRef[] = [];
  for (const ctx of ctxs) {
    for (const h of ctx.comp.highlights ?? []) {
      if (h.kind !== kind) continue;
      const change = ctx.changes.get(h.change_id);
      if (change) out.push({ ctx, h, change });
    }
  }
  return out;
}

/** Final tie-breaks shared by every highlight order: ticker, change id, sentence ids. */
function cmpHighlightIdentity(a: HighlightRef, b: HighlightRef): number {
  return (
    cmpStr(a.ctx.company.ticker, b.ctx.company.ticker) ||
    cmpStr(a.h.change_id, b.h.change_id) ||
    cmpStr(a.h.new_sentence_id ?? "", b.h.new_sentence_id ?? "") ||
    cmpStr(a.h.old_sentence_id ?? "", b.h.old_sentence_id ?? "")
  );
}

/** Potential became actual: change score desc, then ticker A-Z. */
function cmpActual(a: HighlightRef, b: HighlightRef): number {
  return cmpDesc(a.change.score, b.change.score) || cmpHighlightIdentity(a, b);
}

/** Figures: dollars, then percentages, then counts, larger first; then change score desc, then ticker. */
function cmpFigureRef(a: HighlightRef, b: HighlightRef): number {
  return cmpFigure(a.h.detail, b.h.detail) || cmpDesc(a.change.score, b.change.score) || cmpHighlightIdentity(a, b);
}

/** Figure highlights whose old side is absent: a figure that appeared, not one that changed. */
function figureAppeared(h: Highlight): boolean {
  return h.kind === "new_figure" && !h.old_sentence_id;
}

/**
 * A figure highlight is usable when the pipeline parsed a value, or at least one of its sentences
 * carries a digit. Some reports mark "new_figure" on sentences with no number at all; those are
 * skipped everywhere in the briefing rather than shown under a "New figure" label.
 */
function usableFigure(r: HighlightRef): boolean {
  if ((r.h.detail ?? "").trim()) return true;
  const idx = r.ctx.comp.sentence_index;
  const text = (r.h.new_sentence_id && idx[r.h.new_sentence_id]?.text) || (r.h.old_sentence_id && idx[r.h.old_sentence_id]?.text) || "";
  return /\d/.test(text);
}

// ---------------------------------------------------------------------------------------
// Support sentences (read first)
// ---------------------------------------------------------------------------------------

/** The change's first validated claim, when the interpretation ran and the claim's citations resolve. */
function validatedClaim(ctx: Ctx, change: Change): string | null {
  if (change.interpretation?.status !== "ok") return null;
  const claim = change.interpretation.claims?.[0];
  if (!claim || !claim.text.trim()) return null;
  const ids = claim.cited_sentence_ids ?? [];
  if (ids.length === 0 || !ids.every((id) => Object.prototype.hasOwnProperty.call(ctx.comp.sentence_index, id))) return null;
  return claim.text.trim();
}

/** "may -> experienced" -> "Last year: 'may'. This year: 'experienced'." */
export function hedgeSupport(detail: string | null | undefined): string {
  const parts = (detail ?? "").split("->").map((s) => s.trim());
  if (parts.length === 2 && parts[0] && parts[1]) return `Last year: '${parts[0]}'. This year: '${parts[1]}'.`;
  return "Language that described this as possible last year describes it as having happened this year.";
}

function dataSupport(kind: ReadFirstItem["kind"], shortTitle: string, detail: string | null | undefined): string {
  switch (kind) {
    case "potential_became_actual":
      return hedgeSupport(detail);
    case "new_figure":
      return detail && detail.trim()
        ? `The figure ${detail.trim()} appears this year in '${shortTitle}' and was not in last year's filing.`
        : `The figure appears this year in '${shortTitle}' and was not in last year's filing.`;
    case "new_risk":
      return "This risk factor was not in last year's filing.";
    case "removed_risk":
      return "This risk factor was in last year's filing and is not in this year's.";
    default:
      return "";
  }
}

function changeItem(kind: ReadFirstItem["kind"], ctx: Ctx, change: Change, detail: string | null | undefined): ReadFirstItem {
  const shortTitle = shortTitleOf(ctx, change);
  const claim = validatedClaim(ctx, change);
  return {
    kind,
    lead: `${ctx.company.name}: ${shortTitle}`,
    support: claim ?? dataSupport(kind, shortTitle, detail),
    supportSource: claim ? "validated_claim" : "data",
    tickers: [ctx.company.ticker],
    changeId: change.id,
    pageRef: 3,
  };
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

// ---------------------------------------------------------------------------------------
// Page 1: read first
// ---------------------------------------------------------------------------------------

/**
 * Read first, in this order of kinds (each skips a risk factor already listed):
 *  1. up to 2 potential-became-actual highlights (change score desc, then ticker);
 *  2. up to 2 figures that appeared (dollars, percentages, counts; larger first);
 *  3. up to 2 spreading topics: newly added by >= 3 selected companies (>= 2 when 2 to 4 are
 *     selected), ranked like page 2;
 *  4. one quiet item for companies with no meaningful change or <= 10% changed (a slot is
 *     reserved for it, so kinds 1 to 3 take at most 5 items when it applies);
 *  5. when fewer than 4 items so far: new risks by score, then dropped risks, up to 5.
 * At most 6 items.
 */
function buildReadFirst(ctxs: Ctx[], topics: FilteredTopic[], nameOf: Map<string, string>): ReadFirstItem[] {
  const items: ReadFirstItem[] = [];
  const used = new Set<string>();
  const quiet = ctxs
    .map((c) => c.company)
    .filter((c) => c.meaningfulChanges === 0 || c.totalRiskFactors === 0 || c.meaningfulChanges / c.totalRiskFactors <= READ_FIRST_QUIET_SHARE)
    .sort((a, b) => a.meaningfulChanges - b.meaningfulChanges || cmpName(a.name, b.name) || cmpStr(a.ticker, b.ticker));
  // The quiet item always fits: kinds 1 to 3 leave it a slot.
  const room = LIMITS.readFirstMax - (quiet.length > 0 ? 1 : 0);
  const key = (r: { ctx: Ctx; change: Change }) => `${r.ctx.company.ticker}:${r.change.id}`;
  const takeChanges = (refs: { ctx: Ctx; change: Change; detail: string | null | undefined }[], kind: ReadFirstItem["kind"], max: number) => {
    let n = 0;
    for (const r of refs) {
      if (n >= max || items.length >= room) break;
      if (used.has(key(r))) continue;
      used.add(key(r));
      items.push(changeItem(kind, r.ctx, r.change, r.detail));
      n++;
    }
  };

  const actuals = highlightsOf(ctxs, "potential_became_actual").sort(cmpActual);
  takeChanges(actuals.map((r) => ({ ctx: r.ctx, change: r.change, detail: r.h.detail })), "potential_became_actual", LIMITS.readFirstPerKind);

  // Only figures with a parsed value lead the briefing; a figure highlight without one still appears
  // on page 3, where the sentence itself carries the number.
  const figures = highlightsOf(ctxs, "new_figure")
    .filter((r) => figureAppeared(r.h) && (r.h.detail ?? "").trim())
    .sort(cmpFigureRef);
  takeChanges(figures.map((r) => ({ ctx: r.ctx, change: r.change, detail: r.h.detail })), "new_figure", LIMITS.readFirstPerKind);

  const n = ctxs.length;
  const spreadMin = n >= 2 && n <= 4 ? 2 : 3;
  for (const t of topics.filter((x) => x.company_count >= spreadMin).slice(0, LIMITS.readFirstPerKind)) {
    if (items.length >= room) break;
    const tickers = [...t.companies].sort(cmpStr);
    const names = tickers.map((x) => nameOf.get(x) ?? x).sort(cmpName);
    items.push({
      kind: "spreading",
      lead: `${topicLabel(t.topic, t.source)}: new language at ${t.company_count} of ${n} companies`,
      support: `Newly added wording at ${joinNames(names)}.`,
      supportSource: "data",
      tickers,
      changeId: null,
      pageRef: 2,
    });
  }

  if (quiet.length > 0) {
    items.push({
      kind: "quiet",
      lead: quiet
        .map((c) =>
          c.meaningfulChanges === 0
            ? `${c.name} changed nothing meaningful (0 of ${c.totalRiskFactors})`
            : `${c.name} changed ${c.meaningfulChanges} of ${c.totalRiskFactors} risk factors`,
        )
        .join("; "),
      support: null,
      supportSource: null,
      tickers: quiet.map((c) => c.ticker),
      changeId: null,
      pageRef: null,
    });
  }

  if (items.length < LIMITS.readFirstFillBelow) {
    const byScore = (type: ChangeType) =>
      ctxs
        .flatMap((ctx) => ctx.comp.changes.filter((c) => c.change_type === type).map((change) => ({ ctx, change, detail: null })))
        .sort((a, b) => cmpDesc(a.change.score, b.change.score) || cmpStr(a.ctx.company.ticker, b.ctx.company.ticker) || cmpStr(a.change.id, b.change.id));
    takeChanges(byScore("new"), "new_risk", Math.max(0, LIMITS.readFirstFillTo - items.length));
    takeChanges(byScore("removed"), "removed_risk", Math.max(0, LIMITS.readFirstFillTo - items.length));
  }
  return items.slice(0, LIMITS.readFirstMax);
}

// ---------------------------------------------------------------------------------------
// Page 2: themes and matrix
// ---------------------------------------------------------------------------------------

function buildTheme(t: FilteredTopic, byTicker: Map<string, Ctx>): Theme {
  const tickers = [...t.companies].sort(cmpStr);
  const candidates: { q: ThemeQuote; score: number }[] = [];
  for (const ticker of tickers) {
    const ctx = byTicker.get(ticker);
    if (!ctx) continue;
    // The example with the highest-score parent change, else the first (stable); only examples
    // whose sentence is in this report's sentence index can be quoted.
    let best: { ex: FilteredTopic["examples"][number]; score: number } | null = null;
    for (const ex of t.examples) {
      if (ex.ticker !== ticker || !ctx.comp.sentence_index[ex.sentence_id]) continue;
      const score = ctx.changes.get(ex.change_id)?.score ?? -1;
      if (!best || score > best.score) best = { ex, score };
    }
    if (!best) continue;
    const { ex } = best;
    const text = ctx.comp.sentence_index[ex.sentence_id].text;
    const change = ctx.changes.get(ex.change_id);
    candidates.push({
      score: best.score,
      q: {
        ticker,
        name: ctx.company.name,
        changeId: ex.change_id,
        shortTitle: change ? shortTitleOf(ctx, change) : displayTitle(ex.short_title, null, ctx.comp.company.name),
        changeType: change?.change_type ?? null,
        quote: { sentenceId: ex.sentence_id, text, spans: text === ex.text ? spansFromOffsets(text, ex.added_spans) : null },
        edgarUrl: ctx.company.newEdgarUrl,
        isFixture: ctx.company.isFixture,
      },
    });
  }
  // Quotes: parent change score desc, then company name.
  candidates.sort((a, b) => cmpDesc(a.score, b.score) || cmpName(a.q.name, b.q.name) || cmpStr(a.q.ticker, b.q.ticker));
  const quotes = candidates.slice(0, LIMITS.themeQuotes).map((c) => c.q);
  const shown = new Set(quotes.map((q) => q.ticker));
  const alsoNamed = tickers
    .filter((x) => !shown.has(x))
    .map((x) => byTicker.get(x)?.company.name ?? x)
    .sort(cmpName);
  return { topic: t.topic, label: topicLabel(t.topic, t.source), companyCount: t.company_count, sentenceCount: t.sentence_count, tickers, quotes, alsoNamed };
}

function buildMatrix(topics: FilteredTopic[], companies: BriefingCompany[]): TopicMatrix | null {
  if (companies.length < 2 || topics.length === 0) return null;
  const top = topics.slice(0, LIMITS.matrixTopics);
  const rows = companies
    .map((c) => ({ ticker: c.ticker, name: c.name, hits: top.map((t) => t.companies.includes(c.ticker)) }))
    .sort((a, b) => cmpDesc(a.hits.filter(Boolean).length, b.hits.filter(Boolean).length) || cmpName(a.name, b.name) || cmpStr(a.ticker, b.ticker));
  return { topics: top.map((t) => ({ topic: t.topic, label: topicLabel(t.topic, t.source), companyCount: t.company_count })), rows };
}

// ---------------------------------------------------------------------------------------
// Page 3: evidence
// ---------------------------------------------------------------------------------------

function beforeAfter(r: HighlightRef): BeforeAfterQuote | null {
  const { ctx, h, change } = r;
  const oldQ = quoteById(ctx.comp, change, h.old_sentence_id);
  const newQ = quoteById(ctx.comp, change, h.new_sentence_id);
  if (!oldQ && !newQ) return null;
  return {
    ticker: ctx.company.ticker,
    name: ctx.company.name,
    changeId: change.id,
    shortTitle: shortTitleOf(ctx, change),
    kind: h.kind,
    detail: h.detail ?? null,
    figureChanged: isFigureChanged(h),
    old: oldQ,
    new: newQ,
    oldEdgarUrl: ctx.company.oldEdgarUrl,
    newEdgarUrl: ctx.company.newEdgarUrl,
    isFixture: ctx.company.isFixture,
  };
}

function riskItem(ctx: Ctx, change: Change): RiskListItem {
  const named = (ctx.comp.highlights ?? []).find((h) => h.kind === "new_named_party" && h.change_id === change.id && h.detail && h.detail.trim());
  return {
    ticker: ctx.company.ticker,
    name: ctx.company.name,
    changeId: change.id,
    title: change.title,
    shortTitle: shortTitleOf(ctx, change),
    changeType: change.change_type,
    note: named ? `names ${named.detail!.trim()}` : null,
  };
}

/** Changes of one type across the selection: score desc, then ticker, then change id. */
function riskList(ctxs: Ctx[], type: ChangeType): RiskListItem[] {
  return ctxs
    .flatMap((ctx) => ctx.comp.changes.filter((c) => c.change_type === type).map((change) => ({ ctx, change })))
    .sort((a, b) => cmpDesc(a.change.score, b.change.score) || cmpStr(a.ctx.company.ticker, b.ctx.company.ticker) || cmpStr(a.change.id, b.change.id))
    .map((r) => riskItem(r.ctx, r.change));
}

function isQuiet(c: BriefingCompany): boolean {
  if (c.meaningfulChanges === 0) return true;
  return c.meaningfulChanges <= QUIET_MAX_CHANGES && c.totalRiskFactors > 0 && c.meaningfulChanges / c.totalRiskFactors <= QUIET_MAX_SHARE;
}

function buildQuiet(ctxs: Ctx[]): QuietCompany[] {
  return ctxs
    .filter((ctx) => isQuiet(ctx.company))
    .map((ctx) => ({
      ticker: ctx.company.ticker,
      name: ctx.company.name,
      changed: ctx.company.meaningfulChanges,
      total: ctx.company.totalRiskFactors,
      items: ctx.comp.changes
        .filter((c) => c.change_type !== "largely_unchanged")
        .sort((a, b) => cmpDesc(a.score, b.score) || cmpStr(a.id, b.id))
        .map((c) => riskItem(ctx, c)),
    }))
    .sort((a, b) => a.changed - b.changed || cmpName(a.name, b.name) || cmpStr(a.ticker, b.ticker));
}

// ---------------------------------------------------------------------------------------
// Page 4: fiscal-year note
// ---------------------------------------------------------------------------------------

function periodParts(iso: string): { year: number; month: number } | null {
  const m = /^(\d{4})-(\d{2})-\d{2}/.exec(iso ?? "");
  if (!m) return null;
  const month = Number(m[2]);
  return month >= 1 && month <= 12 ? { year: Number(m[1]), month } : null;
}

/**
 * Null when every company's latest fiscal year ends in December. Otherwise names each
 * non-calendar fiscal year and how many companies report on a calendar year.
 */
export function fiscalYearNote(companies: BriefingCompany[]): string | null {
  const off: { c: BriefingCompany; year: number; month: number }[] = [];
  let calendar = 0;
  for (const c of companies) {
    const p = periodParts(c.newPeriodEnd);
    if (!p) continue;
    if (p.month === 12) calendar++;
    else off.push({ c, ...p });
  }
  if (off.length === 0) return null;
  const phrases = off.map((x, i) => `${x.c.name}'s FY${x.c.newFiscalYear} ${i === 0 ? "ended in " : "in "}${MONTHS[x.month - 1]} ${x.year}`);
  const calendarPart = calendar > 0 ? `, while ${calendar} ${calendar === 1 ? "company reports" : "companies report"} on a calendar year` : "";
  if (companies.length === 1) return `${phrases[0]}. 'This year' means its most recent 10-K.`;
  const months = new Set(off.map((x) => x.month));
  const lead = months.size > 1 || calendar > 0 ? "Fiscal years differ by company: " : "Fiscal years do not follow the calendar: ";
  return `${lead}${joinNames(phrases)}${calendarPart}. 'This year' always means each company's most recent 10-K.`;
}

// ---------------------------------------------------------------------------------------
// The model
// ---------------------------------------------------------------------------------------

export function buildBriefing(input: BriefingInput): BriefingModel {
  const ctxs: Ctx[] = input.comparisons.map((comp) => ({ comp, company: companyOf(comp), changes: new Map(comp.changes.map((c) => [c.id, c] as const)) }));
  const companies = ctxs.map((x) => x.company);
  const byTicker = new Map(ctxs.map((x) => [x.company.ticker, x] as const));
  const nameOf = new Map(companies.map((c) => [c.ticker, c.name] as const));

  // Headline.
  const wordsThisYear = companies.reduce((s, x) => s + x.wordsThisYear, 0);
  const changed = companies.reduce((s, x) => s + x.meaningfulChanges, 0);
  const total = companies.reduce((s, x) => s + x.totalRiskFactors, 0);
  const appeared = highlightsOf(ctxs, "new_figure").filter((r) => figureAppeared(r.h) && usableFigure(r)).sort(cmpFigureRef);
  // Headline examples: dollar amounts only (the tile reads "newly disclosed figures: $4.5 billion and
  // $800 million"); other figures are counted but not named here. They are listed in full on page 3.
  const figureExamples: string[] = [];
  for (const r of appeared) {
    const d = (r.h.detail ?? "").trim();
    if (d && d.includes("$") && !figureExamples.includes(d) && figureExamples.length < LIMITS.figureExamples) figureExamples.push(d);
  }
  const headline: HeadlineStats = {
    wordsThisYear,
    readingHours: Math.round((wordsThisYear / 250 / 60) * 10) / 10,
    changed,
    totalRiskFactors: total,
    unchanged: total - changed,
    newCount: companies.reduce((s, x) => s + x.newCount, 0),
    droppedCount: companies.reduce((s, x) => s + x.droppedCount, 0),
    newFigures: { count: appeared.length, examples: figureExamples },
  };

  // Trends restricted to the selection, then ranked.
  const filtered = filterTrends(input.trends, new Map(companies.map((c) => [c.ticker, c.analysisId] as const)));
  const topics = [...filtered.topics].sort(compareTopics);

  const coverage: CoverageRow[] = [...companies]
    .sort((a, b) => cmpDesc(a.meaningfulChanges, b.meaningfulChanges) || cmpName(a.name, b.name) || cmpStr(a.ticker, b.ticker))
    .map((x) => ({
      ticker: x.ticker,
      name: x.name,
      fyLabel: fyLabel(x),
      changed: x.meaningfulChanges,
      total: x.totalRiskFactors,
      mix: { ...x.byChangeType },
      newCount: x.newCount,
      droppedCount: x.droppedCount,
      wordsThisYear: x.wordsThisYear,
      wordsDelta: x.wordsThisYear - x.wordsLastYear,
    }));

  const themes = topics.slice(0, LIMITS.themes).map((t) => buildTheme(t, byTicker));
  const matrix = buildMatrix(topics, companies);

  const actualsAll = highlightsOf(ctxs, "potential_became_actual")
    .sort(cmpActual)
    .map(beforeAfter)
    .filter((x): x is BeforeAfterQuote => x !== null);
  const figuresAll = highlightsOf(ctxs, "new_figure")
    .filter(usableFigure)
    .sort(cmpFigureRef)
    .map(beforeAfter)
    .filter((x): x is BeforeAfterQuote => x !== null);
  const actuals = actualsAll.slice(0, LIMITS.actuals);
  const figures = figuresAll.slice(0, LIMITS.figures);
  const newAll = riskList(ctxs, "new");
  const droppedAll = riskList(ctxs, "removed");
  const newRisks = newAll.slice(0, LIMITS.riskList);
  const droppedRisks = droppedAll.slice(0, LIMITS.riskList);

  const audit: AuditRow[] = companies.map((x) => ({
    ticker: x.ticker,
    name: x.name,
    fyLabel: fyLabel(x),
    latestFiled: x.newFilingDate,
    accession: x.newAccession,
    edgarUrl: x.newEdgarUrl,
    analysisId: x.analysisId,
    isFixture: x.isFixture,
  }));

  // Notes, in a fixed order.
  const notes: string[] = [];
  if (input.missingTickers.length > 0) notes.push(`Not in the library: ${input.missingTickers.join(", ")}.`);
  const fixtures = companies.filter((c) => c.isFixture);
  if (fixtures.length > 0) {
    notes.push(`Includes synthetic FIXTURE data for development, not a real filing: ${fixtures.map((c) => c.ticker).join(", ")}.`);
  }
  if (filtered.staleTickers.length > 0) {
    notes.push(`The topic index was computed from an older report for ${filtered.staleTickers.map((t) => nameOf.get(t) ?? t).join(", ")}, so their topics are not counted.`);
  }
  if (!input.trends) {
    notes.push("The topic index was not available when this briefing was built, so page 2 is omitted.");
  } else if (themes.length === 0) {
    notes.push(
      companies.length === 1
        ? `No newly added topics were found for ${companies[0].name}, so page 2 is omitted.`
        : "No shared topics among these companies, so page 2 is omitted.",
    );
  } else {
    notes.push(
      "Topics are keyword matches on newly added wording (a fixed topic list, named entities and repeated phrases). A shared topic means shared language, not the same exposure.",
    );
    if (topics.slice(0, Math.max(LIMITS.themes, matrix ? LIMITS.matrixTopics : 0)).some((t) => t.partialCount)) {
      notes.push("Sentence counts for a topic used by companies outside this briefing count one example sentence per company shown here.");
    }
  }
  if (actualsAll.length === 0) notes.push("No risk factor moved from possible to actual language in these filings.");
  else if (actualsAll.length > actuals.length) notes.push(`Showing ${actuals.length} of ${actualsAll.length} possible-to-actual changes; the rest are in each company's report.`);
  if (figuresAll.length === 0) notes.push("No new or changed figures were highlighted in these filings.");
  else if (figuresAll.length > figures.length) notes.push(`Showing ${figures.length} of ${figuresAll.length} highlighted figures; the rest are in each company's report.`);
  if (newAll.length === 0) notes.push("No new risk factors in these filings.");
  if (droppedAll.length === 0) notes.push("No dropped risk factors in these filings.");
  const noAi = companies.filter((c) => c.interpretationStatus !== "ok");
  if (noAi.length > 0) {
    notes.push(`AI interpretation was not available for ${joinNames(noAi.map((c) => c.name))}; summary lines for ${noAi.length === 1 ? "it" : "them"} are built from data only.`);
  }

  return {
    templateVersion: BRIEFING_TEMPLATE_VERSION,
    briefingId: briefingId(companies.map((x) => x.analysisId)),
    generatedAt: input.generatedAt,
    libraryAsOf: input.trends?.computed_at ?? null,
    title: input.title,
    preparedFor: input.preparedFor,
    companies,
    headline,
    readFirst: buildReadFirst(ctxs, topics, nameOf),
    coverage,
    themes,
    matrix,
    actuals,
    figures,
    newRisks,
    newRisksOmitted: newAll.length - newRisks.length,
    droppedRisks,
    droppedRisksOmitted: droppedAll.length - droppedRisks.length,
    quiet: buildQuiet(ctxs),
    questions: buildQuestions(actuals, figures, newRisks, droppedRisks),
    audit,
    fiscalYearNote: fiscalYearNote(companies),
    notes,
    hasFixture: companies.some((x) => x.isFixture),
    missingTickers: [...input.missingTickers],
  };
}
