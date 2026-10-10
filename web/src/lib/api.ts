/**
 * Live-mode client for the RiskDiff FastAPI backend. Usable from server and client code.
 * Only NEXT_PUBLIC_API_URL is read here (public by design; it holds no secret).
 */
import type { Comparison } from "@/types/comparison";
import type {
  AnalyzeComplete,
  AnalyzeErrorEvent,
  CompanyCard,
  StageEvent,
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

/** Returns null on 404. Throws ApiUnreachableError / ApiHttpError otherwise. */
export async function getComparisonFromApi(ticker: string): Promise<Comparison | null> {
  const res = await fetchWithTimeout(`${API_BASE}/comparison/${encodeURIComponent(ticker)}`, {
    cache: "no-store",
    timeoutMs: 8000,
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiHttpError(res.status, await readDetail(res));
  return (await res.json()) as Comparison;
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
