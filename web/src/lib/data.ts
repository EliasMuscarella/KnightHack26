import "server-only";

/**
 * Server-only data access (uses node:fs). Cached mode reads published comparison files;
 * live mode falls back to the FastAPI backend. Never import from a client component.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { cache } from "react";

import type { Comparison } from "@/types/comparison";
import { pickHero, type HeroPick } from "@/lib/hero";
import { displayName } from "@/lib/names";
import { pickSpecimens, type Specimen } from "@/lib/specimen";
import {
  ApiUnreachableError,
  getComparisonFromApi,
  getCompaniesFromApi,
  getLibraryStatusFromApi,
  getTrendsFromApi,
  looksLikeComparison,
} from "@/lib/api";
import type { CompanyCard, CompanyListing, LibraryStatus, RubricFile, TrendsPayload } from "@/lib/types";
import { factDetail, isFigureChanged } from "@/lib/vocabulary";

const FILE_RE = /^([A-Z.\-]{1,6})_(\d{4})_(\d{4})\.json$/;

export function publishedDir(): string {
  return process.env.RISKDIFF_PUBLISHED_DIR ?? path.resolve(/*turbopackIgnore: true*/ process.cwd(), "../data/published");
}

function fixturePath(): string {
  return path.resolve(/*turbopackIgnore: true*/ process.cwd(), "../contract/fixtures/FIXTURE_comparison.json");
}

export function fixtureEnabled(): boolean {
  return process.env.RISKDIFF_SHOW_FIXTURE === "1";
}

interface CachedFile {
  mtimeMs: number;
  size: number;
  comparison: Comparison;
}

// Process-level cache keyed by path; invalidated whenever mtime or size changes.
const fileCache = new Map<string, CachedFile>();

async function readComparisonFile(file: string): Promise<Comparison | null> {
  let stat;
  try {
    stat = await fs.stat(file);
  } catch {
    return null;
  }
  const hit = fileCache.get(file);
  if (hit && hit.mtimeMs === stat.mtimeMs && hit.size === stat.size) return hit.comparison;
  try {
    const parsed: unknown = JSON.parse(await fs.readFile(file, "utf8"));
    if (!looksLikeComparison(parsed)) {
      console.warn(`[riskdiff] ignoring ${path.basename(file)}: not a Comparison`);
      return null;
    }
    fileCache.set(file, { mtimeMs: stat.mtimeMs, size: stat.size, comparison: parsed });
    return parsed;
  } catch {
    console.warn(`[riskdiff] ignoring ${path.basename(file)}: unreadable JSON`);
    return null;
  }
}

interface PublishedEntry {
  ticker: string;
  oldFY: number;
  newFY: number;
  file: string;
  name: string;
}

/** Published files, newest fiscal-year pair per ticker. Missing directory → []. */
async function listPublishedEntries(): Promise<PublishedEntry[]> {
  const dir = publishedDir();
  let names: string[];
  try {
    names = await fs.readdir(/*turbopackIgnore: true*/ dir);
  } catch {
    return [];
  }
  const best = new Map<string, PublishedEntry>();
  for (const name of names) {
    const m = FILE_RE.exec(name);
    if (!m) continue;
    const entry = {
      ticker: m[1],
      oldFY: Number(m[2]),
      newFY: Number(m[3]),
      file: path.join(/*turbopackIgnore: true*/ dir, name),
      name,
    };
    const prev = best.get(entry.ticker);
    if (!prev || entry.newFY > prev.newFY || (entry.newFY === prev.newFY && entry.oldFY > prev.oldFY)) {
      best.set(entry.ticker, entry);
    }
  }
  return [...best.values()].sort((a, b) => a.ticker.localeCompare(b.ticker));
}

/**
 * A file from the PUBLISHED directory. Defense in depth: a fixture is never served from
 * there (only contract/fixtures/FIXTURE_comparison.json, and only with RISKDIFF_SHOW_FIXTURE=1),
 * and the file's company.ticker must match the ticker in its filename.
 */
async function readPublishedFile(entry: PublishedEntry): Promise<Comparison | null> {
  const c = await readComparisonFile(entry.file);
  if (!c) return null;
  if (c.is_fixture === true) {
    console.warn(`[riskdiff] ignoring ${entry.name}: fixture data in the published directory`);
    return null;
  }
  if (c.company.ticker !== entry.ticker) {
    console.warn(`[riskdiff] ignoring ${entry.name}: company.ticker does not match the filename`);
    return null;
  }
  return c;
}

function topHighlight(c: Comparison): CompanyListing["top_highlight"] {
  for (const h of c.highlights ?? []) {
    const change = c.changes.find((ch) => ch.id === h.change_id);
    if (change) return { kind: h.kind, short_title: h.short_title, title: change.title, figure_changed: isFigureChanged(h), detail: factDetail(h) };
  }
  return null;
}

function toListing(c: Comparison, file: string, source: CompanyListing["source"]): CompanyListing {
  return {
    ticker: c.company.ticker,
    name: c.company.name,
    cik: c.company.cik,
    old_fiscal_year: c.old_filing.fiscal_year,
    new_fiscal_year: c.new_filing.fiscal_year,
    old_filing_date: c.old_filing.filing_date,
    new_filing_date: c.new_filing.filing_date,
    total_changes: c.summary.total_changes,
    by_change_type: c.summary.by_change_type ?? {},
    max_score: c.summary.max_score,
    file,
    is_fixture: c.is_fixture === true,
    source,
    top_highlight: topHighlight(c),
    analysis_id: c.analysis_id,
  };
}

/** Listing for the home grid: published files (+ FIXTURE in dev) (+ API extras if it is up). */
/** API company cards are untrusted input: require the fields the grid renders and never list fixtures. */
function isUsableCard(card: Partial<CompanyCard> | null | undefined): card is CompanyCard {
  if (!card || typeof card !== "object") return false;
  if (card.is_fixture === true) return false;
  if (typeof card.ticker !== "string" || !/^[A-Z.\-]{1,6}$/.test(card.ticker)) return false;
  if (typeof card.name !== "string" || !card.name) return false;
  if (!card.by_change_type || typeof card.by_change_type !== "object") return false;
  if (typeof card.old_fiscal_year !== "number" || typeof card.new_fiscal_year !== "number") return false;
  if (typeof card.total_changes !== "number") return false;
  return true;
}

type LibraryFields = Pick<CompanyListing, "analysis_id" | "published_by" | "published_at" | "library_source">;

/**
 * Shared-library fields of an API card, read defensively (the card is untrusted input and
 * older API versions do not send them). Only well-formed values are kept.
 */
function libraryFields(card: CompanyCard): LibraryFields {
  const raw = card as unknown as Record<string, unknown>;
  const out: LibraryFields = {};
  if (typeof raw.analysis_id === "string" && /^[0-9a-f]{16,128}$/i.test(raw.analysis_id)) out.analysis_id = raw.analysis_id;
  if (typeof raw.published_by === "string" && raw.published_by.trim()) out.published_by = raw.published_by.trim().slice(0, 80);
  if (typeof raw.published_at === "string" && /^\d{4}-\d{2}-\d{2}/.test(raw.published_at)) out.published_at = raw.published_at;
  if (raw.source === "local" || raw.source === "remote") out.library_source = raw.source;
  return out;
}

export const listCompanies = cache(async (): Promise<CompanyListing[]> => {
  const out: CompanyListing[] = [];
  const seen = new Set<string>();
  for (const entry of await listPublishedEntries()) {
    const c = await readPublishedFile(entry);
    if (!c) continue;
    out.push(toListing(c, entry.name, "published"));
    seen.add(entry.ticker);
  }
  try {
    for (const card of await getCompaniesFromApi()) {
      if (!isUsableCard(card)) continue;
      const lib = libraryFields(card);
      if (seen.has(card.ticker)) {
        // Local file already listed: attach the API's library metadata, but only when the
        // card describes the same comparison (same fiscal-year pair and, when both carry
        // one, the same analysis id), so "Published by" never labels a different report.
        const i = out.findIndex((l) => l.ticker === card.ticker);
        if (i < 0) continue;
        const local = out[i];
        const sameReport =
          local.old_fiscal_year === card.old_fiscal_year &&
          local.new_fiscal_year === card.new_fiscal_year &&
          (!lib.analysis_id || !local.analysis_id || lib.analysis_id === local.analysis_id);
        if (sameReport) out[i] = { ...local, ...lib };
        continue;
      }
      out.push({
        ticker: card.ticker,
        name: card.name,
        cik: card.cik,
        old_fiscal_year: card.old_fiscal_year,
        new_fiscal_year: card.new_fiscal_year,
        old_filing_date: card.old_filing_date,
        new_filing_date: card.new_filing_date,
        total_changes: card.total_changes,
        by_change_type: card.by_change_type,
        max_score: card.max_score,
        file: card.file,
        is_fixture: false,
        source: "api",
        ...lib,
      });
      seen.add(card.ticker);
    }
  } catch {
    // API down: cached mode only.
  }
  if (fixtureEnabled()) {
    const fx = await readComparisonFile(fixturePath());
    if (fx && !seen.has(fx.company.ticker)) out.push(toListing(fx, "FIXTURE_comparison.json", "fixture"));
  }
  return out;
});

/**
 * Tickers that already have a comparison: published files, the FIXTURE in dev, and the
 * tickers the API reports via GET /companies (short timeout; skipped when the API is down).
 */
export async function listKnownTickers(): Promise<string[]> {
  const tickers: string[] = [];
  for (const entry of await listPublishedEntries()) {
    if (await readPublishedFile(entry)) tickers.push(entry.ticker);
  }
  if (fixtureEnabled()) {
    const fx = await readComparisonFile(fixturePath());
    if (fx) tickers.push(fx.company.ticker);
  }
  try {
    for (const card of await getCompaniesFromApi(1500)) {
      if (typeof card?.ticker === "string" && card.is_fixture !== true) tickers.push(card.ticker);
    }
  } catch {
    // API down or slow: cached tickers only.
  }
  return [...new Set(tickers)];
}

/** Shared-library connection state for the footer and audit trail (request-cached, never throws). */
export const getLibraryStatus = cache(async (): Promise<LibraryStatus> => getLibraryStatusFromApi(1500));

/** Cross-company trends from the shared library, or null when the API cannot provide them. */
export const getTrends = cache(async (): Promise<TrendsPayload | null> => getTrendsFromApi(4000));

export interface ComparisonResult {
  comparison: Comparison;
  source: "published" | "fixture" | "api";
}

/** Published directory first, then the FIXTURE (dev only), then the API, else null. */
export const getComparison = cache(async (ticker: string): Promise<ComparisonResult | null> => {
  const entry = (await listPublishedEntries()).find((e) => e.ticker === ticker);
  if (entry) {
    const c = await readPublishedFile(entry);
    if (c) return { comparison: c, source: "published" };
  }
  if (fixtureEnabled()) {
    const fx = await readComparisonFile(fixturePath());
    if (fx && fx.company.ticker === ticker) return { comparison: fx, source: "fixture" };
  }
  try {
    const c = await getComparisonFromApi(ticker);
    if (c && c.is_fixture !== true) return { comparison: c, source: "api" };
  } catch (err) {
    if (!(err instanceof ApiUnreachableError)) {
      console.warn(`[riskdiff] API lookup for ${ticker} failed: ${(err as Error).message}`);
    }
  }
  return null;
});

function looksLikeRubric(x: unknown): x is RubricFile {
  if (!x || typeof x !== "object") return false;
  const r = x as Partial<RubricFile>;
  return Array.isArray(r.weights) && Array.isArray(r.questions);
}

function numericRecord(x: unknown): Record<string, number> {
  if (!x || typeof x !== "object" || Array.isArray(x)) return {};
  return Object.fromEntries(Object.entries(x).filter((e): e is [string, number] => typeof e[1] === "number"));
}

/** contract/rubric.json, or null when it has not been generated yet. */
export async function getRubric(): Promise<RubricFile | null> {
  try {
    const raw: unknown = JSON.parse(
      await fs.readFile(path.resolve(/*turbopackIgnore: true*/ process.cwd(), "../contract/rubric.json"), "utf8"),
    );
    if (!looksLikeRubric(raw)) return null;
    return {
      rubric_version: String(raw.rubric_version ?? "unknown"),
      pipeline_version: String(raw.pipeline_version ?? "unknown"),
      questions: raw.questions,
      weights: raw.weights,
      banned_phrases: Array.isArray(raw.banned_phrases) ? raw.banned_phrases : [],
      thresholds: raw.thresholds && typeof raw.thresholds === "object" ? raw.thresholds : {},
      caps: numericRecord(raw.caps),
    };
  } catch {
    return null;
  }
}

/** ../EVAL.md as raw markdown text, or null when evaluation has not been run. */
export async function getEvalMarkdown(): Promise<string | null> {
  try {
    const text = await fs.readFile(path.resolve(/*turbopackIgnore: true*/ process.cwd(), "../EVAL.md"), "utf8");
    return text.trim() ? text : null;
  } catch {
    return null;
  }
}


/**
 * The home hero's before/after: the top "Potential became actual" highlight across the local
 * published reports (lib/hero.ts). Fixture data is never used, even when it is listed.
 */
export const getHero = cache(async (): Promise<HeroPick | null> => {
  const comparisons: Comparison[] = [];
  for (const entry of await listPublishedEntries()) {
    const c = await readPublishedFile(entry);
    if (c) comparisons.push(c);
  }
  return pickHero(comparisons);
});

/**
 * The home hero's rotating before/after examples: one real change per kind of highlight across the
 * local published reports (lib/specimen.ts), with display names. Fixture data is never used.
 */
export const getSpecimens = cache(async (): Promise<Specimen[]> => {
  const comparisons: Comparison[] = [];
  for (const entry of await listPublishedEntries()) {
    const c = await readPublishedFile(entry);
    if (c) comparisons.push(c);
  }
  return pickSpecimens(comparisons).map((x) => ({ ...x, company: displayName(x.company) || x.ticker }));
});
