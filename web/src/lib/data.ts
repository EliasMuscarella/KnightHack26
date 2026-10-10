import "server-only";

/**
 * Server-only data access (uses node:fs). Cached mode reads published comparison files;
 * live mode falls back to the FastAPI backend. Never import from a client component.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { cache } from "react";

import type { Comparison } from "@/types/comparison";
import { ApiUnreachableError, getComparisonFromApi, getCompaniesFromApi, looksLikeComparison } from "@/lib/api";
import type { CompanyListing, RubricFile } from "@/lib/types";

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
  };
}

/** Listing for the home grid: published files (+ FIXTURE in dev) (+ API extras if it is up). */
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
      if (seen.has(card.ticker)) continue;
      out.push({ ...card, is_fixture: false, source: "api" });
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
