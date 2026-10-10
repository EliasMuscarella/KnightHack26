"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { TickerSearch } from "@/components/TickerSearch";
import { normalizeTicker } from "@/lib/ticker";

/** Not-found UI. Under /c/{TICKER} it offers a live analysis of that ticker. */
export function NotFoundPanel({ kind = "page" }: { kind?: "page" | "comparison" | "change" }) {
  const pathname = usePathname() ?? "";
  const parts = pathname.split("/").filter(Boolean);
  const ticker = parts[0] === "c" ? normalizeTicker(parts[1]) : null;

  const title =
    kind === "change"
      ? "This change is not part of the comparison."
      : kind === "comparison"
        ? ticker
          ? `No published comparison for ${ticker}.`
          : "No comparison for this ticker."
        : "Page not found.";

  return (
    <div className="mx-auto max-w-[760px] px-8 py-20">
      <p className="font-mono text-sm font-semibold text-ink-faint">404</p>
      <h1 className="mt-2 text-3xl font-bold text-ink">{title}</h1>
      <div className="mt-4 space-y-3 text-ink-muted">
        {kind === "change" && ticker ? (
          <p>
            The change id may come from a different analysis version.{" "}
            <Link href={`/c/${encodeURIComponent(ticker)}`} className="font-medium text-accent underline">
              Back to the {ticker} overview
            </Link>
          </p>
        ) : null}
        {kind === "comparison" ? (
          <p>
            Nothing is published for this ticker yet, and the live API did not return one.
            {ticker ? (
              <>
                {" "}
                You can{" "}
                <Link href={`/analyze/${encodeURIComponent(ticker)}`} className="font-medium text-accent underline">
                  analyze {ticker} live
                </Link>{" "}
                if the RiskDiff API is running.
              </>
            ) : null}
          </p>
        ) : null}
        {kind === "page" ? <p>The address may be mistyped, or the page has moved.</p> : null}
      </div>
      <div className="mt-8 max-w-[560px]">
        <TickerSearch size="large" />
      </div>
      <p className="mt-6 text-sm">
        <Link href="/" className="text-accent underline">
          ← Home
        </Link>
      </p>
    </div>
  );
}

/** Error boundary UI shared by every route's error.tsx. */
export function ErrorPanel({ error, retry, context }: { error: Error & { digest?: string }; retry: () => void; context: string }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="mx-auto max-w-[760px] px-8 py-20" role="alert">
      <p className="font-mono text-sm font-semibold text-del-fg">
        <span aria-hidden="true">✕ </span>Error
      </p>
      <h1 className="mt-2 text-3xl font-bold text-ink">Something went wrong while loading {context}.</h1>
      <p className="mt-4 text-ink-muted">
        The published comparison files may be unreadable, or the server hit an unexpected problem. Nothing about the
        filings themselves is affected.
      </p>
      {error.digest ? (
        <p className="mt-2 text-sm text-ink-faint">
          Reference: <span className="font-mono">{error.digest}</span>
        </p>
      ) : null}
      <div className="mt-8 flex gap-3">
        <button
          type="button"
          onClick={() => retry()}
          className="rounded-md bg-accent px-5 py-2 font-semibold text-white hover:bg-accent-strong"
        >
          Try again
        </button>
        <Link href="/" className="rounded-md border border-line-strong bg-surface px-5 py-2 font-semibold text-ink hover:border-ink">
          Home
        </Link>
      </div>
    </div>
  );
}
