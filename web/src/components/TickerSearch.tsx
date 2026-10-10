"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { normalizeTicker, TICKER_HELP } from "@/lib/ticker";

interface Props {
  size?: "compact" | "large";
  /** Tickers known to have a cached comparison (skips a lookup when provided). */
  knownTickers?: string[];
  autoFocus?: boolean;
}

async function fetchKnownTickers(): Promise<string[] | null> {
  try {
    const res = await fetch("/api/known-tickers", { cache: "no-store" });
    if (!res.ok) return null;
    const body = (await res.json()) as { tickers?: unknown };
    return Array.isArray(body.tickers) ? body.tickers.filter((t): t is string => typeof t === "string") : null;
  } catch {
    return null;
  }
}

export function TickerSearch({ size = "large", knownTickers, autoFocus }: Props) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputId = useId();
  const errorId = useId();
  const compact = size === "compact";

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const ticker = normalizeTicker(value);
    if (!ticker) {
      setError(value.trim() ? `"${value.trim()}" is not a valid ticker. ${TICKER_HELP}` : "Enter a ticker symbol.");
      return;
    }
    setError(null);
    setBusy(true);
    const known = knownTickers ?? (await fetchKnownTickers());
    setBusy(false);
    setValue("");
    if (known === null || known.includes(ticker)) {
      // Cached (or unknown because the lookup failed): the overview tries cache, then the API.
      router.push(`/c/${encodeURIComponent(ticker)}`);
    } else {
      router.push(`/analyze/${encodeURIComponent(ticker)}`);
    }
  }

  return (
    <form onSubmit={onSubmit} role="search" aria-label="Look up a company by ticker" noValidate>
      <div className={compact ? "relative flex items-center" : "flex items-stretch gap-3"}>
        <label htmlFor={inputId} className="sr-only">
          Ticker symbol
        </label>
        <input
          id={inputId}
          name="ticker"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          autoFocus={autoFocus}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={12}
          placeholder={compact ? "Ticker, e.g. NVDA" : "Enter a ticker, e.g. NVDA"}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={
            compact
              ? "h-9 w-full rounded-md border border-line-input bg-surface pl-3 pr-20 text-sm uppercase placeholder:normal-case placeholder:text-ink-secondary focus:border-accent focus:outline-none"
              : "h-14 w-full rounded-md border border-line-input bg-surface px-5 text-lg uppercase placeholder:normal-case placeholder:text-ink-secondary focus:border-accent focus:outline-none"
          }
        />
        <button
          type="submit"
          disabled={busy}
          className={
            compact
              ? "absolute right-1 h-7 rounded-sm bg-accent px-3 text-xs font-medium text-on-accent hover:bg-accent-strong disabled:opacity-60"
              : "h-14 shrink-0 rounded-md bg-accent px-7 text-base font-medium text-on-accent hover:bg-accent-strong disabled:opacity-60"
          }
        >
          {busy ? "…" : compact ? "Go" : "Compare filings"}
        </button>
      </div>
      <p
        id={errorId}
        role="alert"
        className={
          error
            ? compact
              ? "absolute mt-1 w-[300px] rounded-md border border-less-fg bg-less-bg px-2 py-1 text-xs text-less-strong-fg"
              : "mt-2 text-sm font-medium text-less-strong-fg"
            : "sr-only"
        }
      >
        {error ? error : null}
      </p>
    </form>
  );
}
