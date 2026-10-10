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
  TrendsCategoryRow,
  TrendsKindRow,
  TrendsPayload,
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

const REMOTE_STATES = ["ok", "offline", "disabled"] as const;

function asRemoteState(x: unknown): Exclude<LibraryStatus, "unknown"> | null {
  return typeof x === "string" && (REMOTE_STATES as readonly string[]).includes(x)
    ? (x as Exclude<LibraryStatus, "unknown">)
    : null;
}

/**
 * GET /store/health. Never throws: a network error, a timeout, a non-2xx response (the
 * endpoint may not exist yet) or an unexpected body all read as "unknown".
 */
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

function isCount(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x >= 0;
}

/**
 * GET /trends, validated row by row (malformed rows are dropped). Never throws: returns
 * null when the API is down, slow, lacks the endpoint, or answers with an unexpected body.
 */
export async function getTrendsFromApi(timeoutMs = 1500): Promise<TrendsPayload | null> {
  let body: unknown;
  try {
    const res = await fetchWithTimeout(`${API_BASE}/trends`, { cache: "no-store", timeoutMs });
    if (!res.ok) return null;
    body = await res.json();
  } catch {
    return null;
  }
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (typeof b.available !== "boolean") return null;
  const byCategory: TrendsCategoryRow[] = (Array.isArray(b.by_category) ? b.by_category : []).filter(
    (r): r is TrendsCategoryRow =>
      !!r &&
      typeof r === "object" &&
      typeof (r as TrendsCategoryRow).category === "string" &&
      typeof (r as TrendsCategoryRow).change_type === "string" &&
      isCount((r as TrendsCategoryRow).companies),
  );
  const byKind: TrendsKindRow[] = (Array.isArray(b.by_kind) ? b.by_kind : []).filter(
    (r): r is TrendsKindRow =>
      !!r &&
      typeof r === "object" &&
      typeof (r as TrendsKindRow).ticker === "string" &&
      /^[A-Z.\-]{1,6}$/.test((r as TrendsKindRow).ticker) &&
      typeof (r as TrendsKindRow).company_name === "string" &&
      typeof (r as TrendsKindRow).kind === "string" &&
      isCount((r as TrendsKindRow).highlights),
  );
  return {
    available: b.available,
    remote: asRemoteState(b.remote) ?? "disabled",
    companies: isCount(b.companies) ? Math.floor(b.companies) : 0,
    by_category: byCategory,
    by_kind: byKind,
  };
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
