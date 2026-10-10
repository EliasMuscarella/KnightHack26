"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { API_BASE, runAnalysis, type AnalyzeOutcome } from "@/lib/api";
import { STAGES } from "@/lib/stages";
import { normalizeTicker } from "@/lib/ticker";
import type { StageEvent } from "@/lib/types";

type StepState = "pending" | "running" | "done" | "cached" | "error";

interface Step {
  state: StepState;
  message: string | null;
}

interface Failure {
  title: string;
  body: string;
  retryable: boolean;
  detail?: string;
}

const ERROR_TITLES: Record<string, { title: string; body: string; retryable: boolean }> = {
  invalid_ticker: { title: "Invalid ticker", body: "The API rejected this ticker symbol.", retryable: false },
  ticker_not_found: {
    title: "Ticker not found",
    body: "SEC EDGAR has no company registered under this ticker. Check the symbol and try again.",
    retryable: false,
  },
  no_10k: {
    title: "Not enough 10-K filings",
    body: "RiskDiff needs two original 10-K filings to compare. This company does not have two on EDGAR (for example, a recent listing or a foreign filer that files 20-F).",
    retryable: false,
  },
  extraction_failed: {
    title: "Could not extract Item 1A",
    body: "The Risk Factors section could not be located reliably in one of the filings, so no comparison was produced rather than a partial one.",
    retryable: false,
  },
  busy: {
    title: "Another analysis is running",
    body: "The server runs one analysis at a time. Wait a moment, then retry.",
    retryable: true,
  },
  timeout: { title: "The analysis timed out", body: "The server stopped the analysis before it finished. Retrying often succeeds because finished stages are cached.", retryable: true },
  sec_unavailable: {
    title: "SEC EDGAR is unavailable",
    body: "The server could not reach SEC EDGAR, or it is not configured with an SEC user agent. Cached comparisons still work.",
    retryable: true,
  },
  internal: { title: "The analysis failed", body: "The server hit an unexpected problem.", retryable: true },
};

function initialSteps(): Step[] {
  return STAGES.map(() => ({ state: "pending", message: null }));
}

function failureFor(outcome: AnalyzeOutcome): Failure | null {
  switch (outcome.kind) {
    case "unreachable":
      return {
        title: "The RiskDiff API is not reachable",
        body: `Live analysis needs the RiskDiff API at ${API_BASE}, and it did not respond. Published comparisons on the home page still work without it.`,
        retryable: true,
        detail: "Start it with: uv run uvicorn api.main:app --port 8000",
      };
    case "http_error": {
      if (outcome.status === 400) return { ...ERROR_TITLES.invalid_ticker, detail: outcome.detail };
      if (outcome.status === 409) return { ...ERROR_TITLES.busy, detail: outcome.detail };
      if (outcome.status === 503) return { ...ERROR_TITLES.sec_unavailable, detail: outcome.detail };
      return { title: "The API returned an error", body: `HTTP ${outcome.status}.`, retryable: true, detail: outcome.detail };
    }
    case "error": {
      const known = ERROR_TITLES[outcome.code] ?? ERROR_TITLES.internal;
      return { ...known, detail: outcome.message };
    }
    case "closed":
      return {
        title: "The connection closed early",
        body: "The progress stream ended before the analysis finished.",
        retryable: true,
      };
    default:
      return null;
  }
}

const STATE_LABEL: Record<StepState, string> = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  cached: "Cached",
  error: "Error",
};

function StepIcon({ state }: { state: StepState }) {
  const base = "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 font-mono text-sm font-bold";
  switch (state) {
    case "running":
      return (
        <span className={`${base} border-accent bg-surface`}>
          <span className="rd-spin block h-4 w-4 rounded-full border-2 border-line-strong border-t-accent" aria-hidden="true" />
        </span>
      );
    case "done":
      return <span className={`${base} border-add-line bg-add-bg text-add-fg`} aria-hidden="true">✓</span>;
    case "cached":
      return <span className={`${base} border-exp-line bg-exp-bg text-exp-fg`} aria-hidden="true">↺</span>;
    case "error":
      return <span className={`${base} border-del-line bg-del-bg text-del-fg`} aria-hidden="true">✕</span>;
    default:
      return <span className={`${base} border-line-strong bg-surface text-ink-faint`} aria-hidden="true">·</span>;
  }
}

export function AnalyzeRunner({ ticker }: { ticker: string }) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [steps, setSteps] = useState<Step[]>(initialSteps);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [phase, setPhase] = useState<"connecting" | "streaming" | "complete" | "failed">("connecting");
  const controllerRef = useRef<AbortController | null>(null);
  const abortTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAttempt = useRef<number | null>(null);

  useEffect(() => {
    // React Strict Mode mounts effects twice in development. A deferred abort lets the
    // remount keep the in-flight request instead of POSTing twice (which would 409).
    if (abortTimer.current) {
      clearTimeout(abortTimer.current);
      abortTimer.current = null;
    }
    const existing = controllerRef.current;
    if (existing && !existing.signal.aborted && startedAttempt.current === attempt) {
      return () => {
        abortTimer.current = setTimeout(() => existing.abort(), 0);
      };
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    startedAttempt.current = attempt;

    const onStage = (ev: StageEvent) => {
      setPhase("streaming");
      if (typeof ev.stage !== "number" || ev.stage < 0 || ev.stage >= STAGES.length) return;
      setSteps((prev) => {
        const next = prev.slice();
        const state: StepState =
          ev.status === "started" ? "running" : ev.status === "done" ? "done" : ev.status === "cached" ? "cached" : "error";
        next[ev.stage] = { state, message: ev.message ?? null };
        // A later stage starting implies earlier running stages finished.
        for (let i = 0; i < ev.stage; i++) if (next[i].state === "running") next[i] = { ...next[i], state: "done" };
        return next;
      });
    };

    runAnalysis(ticker, { onStage }, controller.signal).then((outcome) => {
      if (controller.signal.aborted || outcome.kind === "aborted") return;
      if (outcome.kind === "complete") {
        setPhase("complete");
        setSteps((prev) => prev.map((s) => (s.state === "running" ? { ...s, state: "done" } : s)));
        const target = normalizeTicker(outcome.payload?.ticker) ?? ticker;
        router.push(`/c/${encodeURIComponent(target)}`);
        return;
      }
      setPhase("failed");
      setFailure(failureFor(outcome));
      setSteps((prev) => prev.map((s) => (s.state === "running" ? { ...s, state: "error" } : s)));
    });

    return () => {
      abortTimer.current = setTimeout(() => controller.abort(), 0);
    };
  }, [ticker, attempt, router]);

  function retry() {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setSteps(initialSteps());
    setFailure(null);
    setPhase("connecting");
    setAttempt((a) => a + 1);
  }

  const doneCount = steps.filter((s) => s.state === "done" || s.state === "cached").length;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_440px] items-start gap-10">
      <section aria-labelledby="progress-heading" className="rounded-lg border border-line bg-surface p-6">
        <div className="flex items-baseline justify-between">
          <h2 id="progress-heading" className="text-lg font-bold text-ink">
            Pipeline progress
          </h2>
          <p className="text-sm text-ink-faint" aria-live="polite">
            {phase === "connecting"
              ? "Connecting to the API…"
              : phase === "streaming"
                ? `${doneCount} of ${STAGES.length} stages finished`
                : phase === "complete"
                  ? "Finished. Opening the comparison…"
                  : "Stopped"}
          </p>
        </div>

        {failure ? (
          <div role="alert" className="mt-4 rounded-md border-l-4 border-del-line bg-del-bg p-4 text-del-fg">
            <p className="font-bold">
              <span aria-hidden="true">✕ </span>
              {failure.title}
            </p>
            <p className="mt-1 text-sm">{failure.body}</p>
            {failure.detail ? (
              <p className="mt-2 rounded bg-surface/70 px-2 py-1 font-mono text-xs text-ink">{failure.detail}</p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-3">
              {failure.retryable ? (
                <button
                  type="button"
                  onClick={retry}
                  className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-white hover:bg-accent-strong"
                >
                  Retry
                </button>
              ) : null}
              <Link href="/" className="rounded-md border border-line-strong bg-surface px-4 py-1.5 text-sm font-semibold text-ink hover:border-ink">
                Browse published comparisons
              </Link>
            </div>
          </div>
        ) : null}

        <ol className="mt-6" aria-label="Pipeline stages">
          {STAGES.map((stage, i) => {
            const step = steps[i];
            const last = i === STAGES.length - 1;
            return (
              <li key={stage.stage} className="relative flex gap-4 pb-5" data-stage={stage.stage} data-state={step.state}>
                {!last ? (
                  <span
                    aria-hidden="true"
                    className={`absolute left-[13px] top-8 h-[calc(100%-2rem)] w-0.5 ${
                      step.state === "done" || step.state === "cached" ? "bg-add-line" : "bg-line"
                    }`}
                  />
                ) : null}
                <StepIcon state={step.state} />
                <div className="min-w-0 flex-1 pt-0.5">
                  <p className="flex items-baseline gap-3">
                    <span className={`font-semibold ${step.state === "pending" ? "text-ink-muted" : "text-ink"}`}>
                      <span className="font-mono text-ink-faint">{stage.stage}</span> {stage.label}
                    </span>
                    <span
                      className={`rounded px-1.5 py-px text-xs font-semibold ${
                        step.state === "error"
                          ? "bg-del-bg text-del-fg"
                          : step.state === "running"
                            ? "bg-accent-bg text-accent-strong"
                            : step.state === "pending"
                              ? "text-ink-faint"
                              : "bg-sunken text-ink-muted"
                      }`}
                    >
                      {STATE_LABEL[step.state]}
                    </span>
                    {stage.kind === "ai" ? (
                      <span className="text-xs font-semibold text-ai-fg">
                        <span aria-hidden="true">✦ </span>AI-assisted
                      </span>
                    ) : null}
                  </p>
                  {step.message ? <p className="mt-0.5 text-sm text-ink-muted">{step.message}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <aside aria-labelledby="explainer-heading" className="rounded-lg border border-line bg-paper p-6">
        <h2 id="explainer-heading" className="text-lg font-bold text-ink">
          What is happening
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          RiskDiff downloads {ticker}&apos;s two most recent 10-K filings from SEC EDGAR and compares their Risk
          Factors sections. What changed is computed by deterministic code. AI is used in two places only: to recognize
          the same risk across years (embeddings) and to answer narrow rubric questions with citations.
        </p>
        <ol className="mt-4 space-y-3 text-sm">
          {STAGES.map((s) => (
            <li key={s.stage} className="flex gap-3">
              <span className="w-4 shrink-0 font-mono font-bold text-ink-faint">{s.stage}</span>
              <span>
                <span className="font-semibold text-ink">{s.label}</span>
                {s.kind === "ai" ? <span className="text-xs font-semibold text-ai-fg"> · AI-assisted</span> : null}
                <span className="block leading-snug text-ink-muted">{s.description}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-xs text-ink-faint">
          Stages already computed for these filings are reused from the cache, so a repeated analysis finishes quickly
          and returns the same result.
        </p>
      </aside>
    </div>
  );
}
