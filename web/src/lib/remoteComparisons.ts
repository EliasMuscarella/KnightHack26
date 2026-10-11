/**
 * Full comparisons for the reports that exist only in the shared library (served by the API,
 * absent from the local published directory). The home hero's specimens and the library cards'
 * "Top change" are computed from full comparisons; without these, a frontend whose library comes
 * entirely from the API (no ../data/published next to it) has no specimens and no top changes.
 *
 * Process-wide memo, one record per ticker, keyed by the API listing's analysis_id:
 * - a record is reused for TTL_MS (failures are retried after RETRY_MS); an expired record keeps
 *   serving its last good comparison while it refreshes in the background (stale-while-revalidate);
 * - a different analysis_id for a ticker drops the old comparison and fetches the new one;
 * - concurrent callers share one in-flight fetch per ticker; at most `concurrency` fetches run at once;
 * - `get(refs, waitMs)` waits at most `waitMs` for tickers that have no comparison yet and then returns
 *   whatever is available; unfinished fetches keep running and fill the memo for the next request. The
 *   wait is counted from when each fetch was requested, so during a slow cold fill only the first
 *   `waitMs` blocks; later requests render at once with what has arrived.
 *
 * API payloads are untrusted: only tickers matching ^[A-Z.\-]{1,6}$ are ever requested, and a payload
 * is kept only when it is shaped like a Comparison, is not a fixture, names the requested ticker and
 * (when the listing gives one) carries the listed analysis_id. Local published files always take
 * precedence for a ticker (`mergeComparisons`).
 *
 * Dependency-free on purpose (type imports only, no "server-only") so node --test can load it.
 */
import type { Comparison } from "@/types/comparison";

const TICKER = /^[A-Z.\-]{1,6}$/;
const ANALYSIS_ID = /^[0-9a-f]{16,128}$/i;

export const TTL_MS = 10 * 60 * 1000;
export const RETRY_MS = 60 * 1000;
export const CONCURRENCY = 4;
/** Upper bound on API-only reports held in memory (first N by ticker, so the choice is deterministic). */
export const MAX_REMOTE = 60;

export interface RemoteRef {
  ticker: string;
  analysisId: string | null;
}

/** The fields of an API company card this module reads; everything else is ignored. */
export interface RemoteCardLike {
  ticker?: unknown;
  analysis_id?: unknown;
  is_fixture?: unknown;
}

/**
 * The API-only reports worth fetching: valid ticker, not a fixture, not available locally. The first
 * card per ticker wins (the same card the library listing shows); sorted by ticker; capped at `max`.
 */
export function remoteRefs(
  cards: Iterable<RemoteCardLike | null | undefined>,
  localTickers: ReadonlySet<string>,
  max = MAX_REMOTE,
): RemoteRef[] {
  const out = new Map<string, RemoteRef>();
  for (const card of cards) {
    if (!card || typeof card !== "object" || card.is_fixture === true) continue;
    const ticker = card.ticker;
    if (typeof ticker !== "string" || !TICKER.test(ticker) || localTickers.has(ticker) || out.has(ticker)) continue;
    const id = card.analysis_id;
    out.set(ticker, { ticker, analysisId: typeof id === "string" && ANALYSIS_ID.test(id) ? id : null });
  }
  return [...out.values()].sort((a, b) => cmp(a.ticker, b.ticker)).slice(0, Math.max(0, max));
}

/** A fetched payload, kept only if it is a non-fixture comparison of exactly the listed report. */
export function acceptRemote(
  ref: RemoteRef,
  payload: unknown,
  validate: (x: unknown) => x is Comparison,
): Comparison | null {
  if (!validate(payload)) return null;
  if (payload.is_fixture === true) return null;
  if (payload.company.ticker !== ref.ticker) return null;
  if (ref.analysisId !== null && payload.analysis_id !== ref.analysisId) return null;
  return payload;
}

/**
 * Local comparisons plus the API ones for tickers that have no local report; one comparison per
 * ticker (the first seen; local always wins), fixtures never, sorted by ticker so the result does not
 * depend on fetch order.
 */
export function mergeComparisons(local: readonly Comparison[], remote: readonly Comparison[]): Comparison[] {
  const byTicker = new Map<string, Comparison>();
  for (const c of [...local, ...remote]) {
    if (c.is_fixture === true) continue;
    const t = c.company.ticker;
    if (!byTicker.has(t)) byTicker.set(t, c);
  }
  return [...byTicker.values()].sort((a, b) => cmp(a.company.ticker, b.company.ticker));
}

function cmp(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Runs at most `n` tasks at once, in submission order. */
export function createLimiter(n: number) {
  let active = 0;
  const queue: (() => void)[] = [];
  const next = () => {
    if (active >= n) return;
    const start = queue.shift();
    if (start) start();
  };
  return function run<T>(task: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      queue.push(() => {
        active++;
        let p: Promise<T>;
        try {
          p = task();
        } catch (err) {
          p = Promise.reject(err);
        }
        p.then(resolve, reject).finally(() => {
          active--;
          next();
        });
      });
      next();
    });
  };
}

/** Resolves after `ms` without keeping the process alive; the timer is cleared by `cancel`. */
function delay(ms: number): { promise: Promise<void>; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const promise = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, ms);
    (timer as { unref?: () => void }).unref?.();
  });
  return { promise, cancel: () => clearTimeout(timer) };
}

export interface RemoteMemoOptions {
  /** Fetches one ticker's comparison; may throw or return anything (the result is validated). */
  fetcher: (ticker: string) => Promise<unknown>;
  validate: (x: unknown) => x is Comparison;
  ttlMs?: number;
  retryMs?: number;
  concurrency?: number;
  now?: () => number;
}

export interface RemoteMemo {
  /**
   * Comparisons for `refs` (sorted by ticker), waiting for the ones not yet in memory until `waitMs`
   * after their fetch was requested (pass the same `waitMs` on every call).
   */
  get(refs: readonly RemoteRef[], waitMs: number): Promise<Comparison[]>;
  /** Number of fetches currently in flight (for tests and diagnostics). */
  inFlight(): number;
}

interface Rec {
  analysisId: string | null;
  value: Comparison | null;
  /** When the last fetch settled; -Infinity before the first one. */
  settledAt: number;
  failed: boolean;
  inflight: Promise<void> | null;
  /** When the current fetch was requested (the bounded wait counts from here). */
  requestedAt: number;
}

export function createRemoteMemo(opts: RemoteMemoOptions): RemoteMemo {
  const ttl = opts.ttlMs ?? TTL_MS;
  const retry = opts.retryMs ?? RETRY_MS;
  const now = opts.now ?? Date.now;
  const limit = createLimiter(Math.max(1, opts.concurrency ?? CONCURRENCY));
  const recs = new Map<string, Rec>();
  let inFlight = 0;

  function ensure(ref: RemoteRef): Rec {
    let rec = recs.get(ref.ticker);
    if (!rec || rec.analysisId !== ref.analysisId) {
      // New ticker, or a different analysis of it: never show the previous report's content.
      rec = { analysisId: ref.analysisId, value: null, settledAt: -Infinity, failed: false, inflight: null, requestedAt: -Infinity };
      recs.set(ref.ticker, rec);
    }
    const fresh = now() - rec.settledAt < (rec.failed || !rec.value ? retry : ttl);
    if (!fresh && !rec.inflight) {
      const target = rec;
      inFlight++;
      target.requestedAt = now();
      target.inflight = limit(() => opts.fetcher(ref.ticker))
        .then(
          (payload) => acceptRemote(ref, payload, opts.validate),
          () => null,
        )
        .then((value) => {
          inFlight--;
          target.inflight = null;
          target.settledAt = now();
          target.failed = value === null;
          if (value) target.value = value; // a failed refresh keeps serving the last good comparison
        });
    }
    return rec;
  }

  return {
    async get(refs, waitMs) {
      const wanted = new Set(refs.map((r) => r.ticker));
      for (const t of [...recs.keys()]) if (!wanted.has(t)) recs.delete(t); // memory stays bounded by the listing
      const records = refs.map(ensure);
      const pending = records.filter((r) => !r.value && r.inflight);
      const t = now();
      const remaining = Math.min(waitMs, Math.max(0, ...pending.map((r) => r.requestedAt + waitMs - t)));
      if (pending.length > 0 && remaining > 0) {
        const timer = delay(remaining);
        await Promise.race([Promise.all(pending.map((r) => r.inflight)), timer.promise]);
        timer.cancel();
      }
      return refs
        .map((r) => recs.get(r.ticker)?.value ?? null)
        .filter((c): c is Comparison => c !== null)
        .sort((a, b) => cmp(a.company.ticker, b.company.ticker));
    },
    inFlight: () => inFlight,
  };
}
