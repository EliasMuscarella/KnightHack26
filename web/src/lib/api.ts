/**
 * Live-mode client for the RiskDiff FastAPI backend. Usable from server and client code.
 * Only NEXT_PUBLIC_API_URL is read here (public by design; it holds no secret).
 */
import type { Comparison } from "@/types/comparison";
import type {
  AnalyzeComplete,
  AnalyzeErrorEvent,
  CompanyCard,
  LibraryStatus,
  StageEvent,
  StoreState,
  TrendsActual,
  TrendsCategoryActivity,
  TrendsCompany,
  TrendsPayload,
  TrendsTopic,
  TrendsTopicExample,
} from "@/lib/types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

export class ApiUnreachableError extends Error {
  constructor(message = "The RiskDiff API is not reachable.") {
    super(message);
    this.name = "ApiUnreachableError";
  }
}

export class ApiHttpError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiHttpError";
    this.status = status;
    this.detail = detail;
  }
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const { timeoutMs = 5000, signal, ...rest } = init;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);
  try {
    return await fetch(url, { ...rest, signal: controller.signal });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new ApiUnreachableError();
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

export async function readDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* not JSON */
  }
  return `HTTP ${res.status}`;
}

export async function getHealth(): Promise<{ status: string; model_warm: boolean }> {
  const res = await fetchWithTimeout(`${API_BASE}/health`, { cache: "no-store", timeoutMs: 2000 });
  if (!res.ok) throw new ApiHttpError(res.status, await readDetail(res));
  return res.json();
}

export async function getCompaniesFromApi(timeoutMs = 1500): Promise<CompanyCard[]> {
  const res = await fetchWithTimeout(`${API_BASE}/companies`, { cache: "no-store", timeoutMs });
  if (!res.ok) throw new ApiHttpError(res.status, await readDetail(res));
  const body = (await res.json()) as { companies?: CompanyCard[] };
  return Array.isArray(body.companies) ? body.companies : [];
}


function asRemoteState(x: unknown): StoreState | null {
  return x === "ok" || x === "offline" || x === "disabled" || x === "connecting" ? x : null;
}

export async function getLibraryStatusFromApi(timeoutMs = 1500): Promise<LibraryStatus> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/store/health`, { cache: "no-store", timeoutMs });
    if (!res.ok) return "unknown";
    const body = (await res.json()) as { remote?: unknown };
    return asRemoteState(body?.remote) ?? "unknown";
  } catch {
    return "unknown";
  }
}


/**
 * GET /trends, validated row by row (malformed rows are dropped). Never throws: returns
 * null when the API is down, slow, lacks the endpoint, or answers with an unexpected body.
 */
const TICKER = /^[A-Z.\-]{1,6}$/;

function str(x: unknown, max = 2000): string | null {
  return typeof x === "string" && x.length <= max ? x : null;
}
function num(x: unknown): number {
  return typeof x === "number" && Number.isFinite(x) && x >= 0 ? x : 0;
}
function counts(x: unknown): Record<string, number> {
  if (!x || typeof x !== "object") return {};
  return Object.fromEntries(Object.entries(x as Record<string, unknown>).filter(([, v]) => typeof v === "number" && Number.isFinite(v))) as Record<string, number>;
}
function spans(x: unknown, len: number): [number, number][] {
  if (!Array.isArray(x)) return [];
  const out: [number, number][] = [];
  for (const p of x) {
    if (!Array.isArray(p) || p.length !== 2) continue;
    const [a, b] = p;
    if (typeof a !== "number" || typeof b !== "number" || a < 0 || b > len || a >= b) continue;
    out.push([Math.floor(a), Math.floor(b)]);
  }
  return out.sort((p, q) => p[0] - q[0]);
}

function company(x: unknown): TrendsCompany | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  const ticker = str(r.ticker, 6);
  if (!ticker || !TICKER.test(ticker)) return null;
  return {
    ticker,
    name: str(r.name, 200) ?? ticker,
    analysis_id: str(r.analysis_id, 64) ?? "",
    old_fiscal_year: num(r.old_fiscal_year),
    new_fiscal_year: num(r.new_fiscal_year),
    total_changes: num(r.total_changes),
    meaningful_changes: num(r.meaningful_changes),
    by_change_type: counts(r.by_change_type),
    cik: str(r.cik, 10),
    old_accession: str(r.old_accession, 32),
    new_accession: str(r.new_accession, 32),
    edgar_url_old: str(r.edgar_url_old, 500),
    edgar_url_new: str(r.edgar_url_new, 500),
  };
}

function example(x: unknown): TrendsTopicExample | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  const ticker = str(r.ticker, 6);
  const text = str(r.text, 5000);
  const changeId = str(r.change_id, 64);
  if (!ticker || !TICKER.test(ticker) || !text || !changeId || !/^[0-9a-f]{8,64}$/.test(changeId)) return null;
  return {
    ticker,
    change_id: changeId,
    sentence_id: str(r.sentence_id, 80) ?? "",
    short_title: str(r.short_title, 300) ?? "",
    status: r.status === "modified" ? "modified" : "added",
    text,
    added_spans: spans(r.added_spans, text.length),
    matched_terms: Array.isArray(r.matched_terms) ? r.matched_terms.filter((t): t is string => typeof t === "string").slice(0, 10) : [],
  };
}

function topic(x: unknown): TrendsTopic | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  const name = str(r.topic, 120);
  if (!name) return null;
  const companies = Array.isArray(r.companies) ? r.companies.filter((t): t is string => typeof t === "string" && TICKER.test(t)) : [];
  return {
    topic: name,
    source: r.source === "entity" || r.source === "phrase" ? r.source : "lexicon",
    company_count: Math.max(num(r.company_count), companies.length),
    sentence_count: num(r.sentence_count),
    companies,
    examples: Array.isArray(r.examples) ? r.examples.map(example).filter((e): e is TrendsTopicExample => e !== null) : [],
  };
}

function activity(x: unknown): TrendsCategoryActivity | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  const ticker = str(r.ticker, 6);
  const category = str(r.category, 80);
  if (!ticker || !TICKER.test(ticker) || !category) return null;
  return {
    ticker,
    category,
    risk_factors: num(r.risk_factors),
    change_ids: Array.isArray(r.change_ids) ? r.change_ids.filter((c): c is string => typeof c === "string") : [],
    added_sentences: num(r.added_sentences),
    removed_sentences: num(r.removed_sentences),
    modified_sentences: num(r.modified_sentences),
    added_words: num(r.added_words),
    removed_words: num(r.removed_words),
    modified_words: num(r.modified_words),
    max_score: num(r.max_score),
  };
}

function actual(x: unknown): TrendsActual | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  const ticker = str(r.ticker, 6);
  const changeId = str(r.change_id, 64);
  if (!ticker || !TICKER.test(ticker) || !changeId) return null;
  return {
    ticker,
    company_name: str(r.company_name, 200) ?? ticker,
    change_id: changeId,
    short_title: str(r.short_title, 300) ?? "",
    old_sentence_id: str(r.old_sentence_id, 80),
    new_sentence_id: str(r.new_sentence_id, 80),
    old_text: str(r.old_text, 5000),
    new_text: str(r.new_text, 5000),
    score: num(r.score),
    old_spans: spans(r.old_spans, (str(r.old_text, 5000) ?? "").length),
    new_spans: spans(r.new_spans, (str(r.new_text, 5000) ?? "").length),
  };
}

/** Validates the /trends payload field by field; anything malformed is dropped, never rendered. */
export function parseTrends(body: unknown): TrendsPayload | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  const status = asRemoteState(b.status);
  if (!status) return null;
  const headline = (b.headline && typeof b.headline === "object" ? b.headline : {}) as Record<string, unknown>;
  const top = headline.top_topic && typeof headline.top_topic === "object" ? (headline.top_topic as Record<string, unknown>) : null;
  const companies = Array.isArray(b.companies) ? b.companies.map(company).filter((c): c is TrendsCompany => c !== null) : [];
  return {
    status,
    source: b.source === "databricks" || b.source === "local" ? b.source : null,
    computed_at: str(b.computed_at, 40),
    companies,
    headline: {
      companies: Math.max(num(headline.companies), companies.length),
      meaningful_changes: num(headline.meaningful_changes),
      top_topic: top && typeof top.topic === "string" ? { topic: top.topic, company_count: num(top.company_count) } : null,
    },
    topics: Array.isArray(b.topics) ? b.topics.map(topic).filter((t): t is TrendsTopic => t !== null) : [],
    category_activity: Array.isArray(b.category_activity) ? b.category_activity.map(activity).filter((a): a is TrendsCategoryActivity => a !== null) : [],
    potential_to_actual: Array.isArray(b.potential_to_actual) ? b.potential_to_actual.map(actual).filter((a): a is TrendsActual => a !== null) : [],
    change_mix: Array.isArray(b.change_mix)
      ? b.change_mix
          .map((m) => (m && typeof m === "object" ? (m as Record<string, unknown>) : null))
          .filter((m): m is Record<string, unknown> => !!m && typeof m.ticker === "string" && TICKER.test(m.ticker))
          .map((m) => ({ ticker: m.ticker as string, by_change_type: counts(m.by_change_type) }))
      : [],
  };
}

/** GET /trends; null when the API is down, slow, or the payload is malformed. */
export async function getTrendsFromApi(timeoutMs = 4000): Promise<TrendsPayload | null> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/trends`, { cache: "no-store", timeoutMs });
    if (!res.ok) return null;
    return parseTrends(await res.json());
  } catch {
    return null;
  }
}

/** Minimal structural check before treating untrusted JSON as a Comparison. */
export function looksLikeComparison(x: unknown): x is Comparison {
  if (!x || typeof x !== "object") return false;
  const c = x as Partial<Comparison>;
  return (
    typeof c.analysis_id === "string" &&
    !!c.company &&
    typeof c.company.ticker === "string" &&
    Array.isArray(c.changes) &&
    !!c.sentence_index &&
    typeof c.sentence_index === "object" &&
    !!c.old_filing &&
    !!c.new_filing &&
    !!c.summary
  );
}

/**
 * Returns null on 404, on a response that is not shaped like a Comparison, or on a
 * comparison for a different ticker. Throws ApiUnreachableError / ApiHttpError otherwise.
 */
export async function getComparisonFromApi(ticker: string): Promise<Comparison | null> {
  const res = await fetchWithTimeout(`${API_BASE}/comparison/${encodeURIComponent(ticker)}`, {
    cache: "no-store",
    timeoutMs: 8000,
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiHttpError(res.status, await readDetail(res));
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return null;
  }
  if (!looksLikeComparison(body) || body.company.ticker !== ticker) return null;
  return body;
}

// ---------------------------------------------------------------------------------------
// POST /analyze: Server-Sent Events over fetch (EventSource cannot POST).
// ---------------------------------------------------------------------------------------

export interface SseMessage {
  event: string;
  data: string;
}

/** Incremental SSE parser: feed text chunks, get complete messages back. */
export function createSseParser(onMessage: (msg: SseMessage) => void) {
  let buffer = "";
  const flushBlock = (block: string) => {
    let event = "message";
    const data: string[] = [];
    for (const rawLine of block.split(/\r\n|\r|\n/)) {
      if (rawLine === "" || rawLine.startsWith(":")) continue;
      const idx = rawLine.indexOf(":");
      const field = idx === -1 ? rawLine : rawLine.slice(0, idx);
      let value = idx === -1 ? "" : rawLine.slice(idx + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length > 0) onMessage({ event, data: data.join("\n") });
  };
  return {
    push(chunk: string) {
      buffer += chunk;
      const parts = buffer.split(/\r\n\r\n|\n\n|\r\r/);
      buffer = parts.pop() ?? "";
      for (const part of parts) flushBlock(part);
    },
    end() {
      if (buffer.trim()) flushBlock(buffer);
      buffer = "";
    },
  };
}

export type AnalyzeOutcome =
  | { kind: "complete"; payload: AnalyzeComplete }
  | { kind: "error"; code: string; message: string }
  | { kind: "http_error"; status: number; detail: string }
  | { kind: "unreachable" }
  | { kind: "closed" }
  | { kind: "aborted" };

export interface AnalyzeHandlers {
  onStage: (ev: StageEvent) => void;
}

/** Starts a live analysis and streams stage events until complete/error/close. */
export async function runAnalysis(
  ticker: string,
  handlers: AnalyzeHandlers,
  signal: AbortSignal,
): Promise<AnalyzeOutcome> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ ticker }),
      signal,
      cache: "no-store",
    });
  } catch {
    return signal.aborted ? { kind: "aborted" } : { kind: "unreachable" };
  }
  if (!res.ok) {
    return { kind: "http_error", status: res.status, detail: await readDetail(res) };
  }
  if (!res.body) return { kind: "closed" };

  let outcome: AnalyzeOutcome | null = null;
  const parser = createSseParser((msg) => {
    if (outcome) return;
    let data: unknown;
    try {
      data = JSON.parse(msg.data);
    } catch {
      return;
    }
    if (msg.event === "stage") {
      handlers.onStage(data as StageEvent);
    } else if (msg.event === "complete") {
      outcome = { kind: "complete", payload: data as AnalyzeComplete };
    } else if (msg.event === "error") {
      const e = data as Partial<AnalyzeErrorEvent>;
      outcome = {
        kind: "error",
        code: typeof e.code === "string" ? e.code : "internal",
        message: typeof e.message === "string" ? e.message : "The analysis failed.",
      };
    }
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (!outcome) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.end();
  } catch {
    if (signal.aborted) return { kind: "aborted" };
    return outcome ?? { kind: "closed" };
  } finally {
    if (outcome) reader.cancel().catch(() => undefined);
  }
  return outcome ?? { kind: "closed" };
}
