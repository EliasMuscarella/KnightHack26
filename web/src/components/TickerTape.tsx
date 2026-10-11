"use client";

/**
 * Home page market-price tape: delayed quotes cached by our API (GET /ticker-tape, proxied at
 * /api/ticker-tape), refreshed once a minute while the tab is visible. Renders nothing when the
 * feed is unavailable or empty, so the page looks exactly as it does without it.
 *
 * Direction uses DESIGN.md's value-neutral families (blue up, orange down, secondary ink flat),
 * never green/red, and every colored change also carries a sign and an arrow. Motion is a
 * CSS-only marquee (globals.css, .tape-*): keeps moving on hover, paused on keyboard focus; under
 * prefers-reduced-motion it is a still, horizontally scrollable row.
 */
import { useEffect, useState, type CSSProperties } from "react";

import {
  formatTapeChange,
  formatTapePrice,
  formatTapeTime,
  parseTickerTape,
  tapeDirection,
  tapeDurationSeconds,
  tapeVisible,
  type TapeDirection,
  type TapeQuote,
  type TickerTapePayload,
} from "@/lib/tickerTape";

const REFRESH_MS = 60_000;

const TONE: Record<TapeDirection, string> = {
  up: "text-more-fg",
  down: "text-less-fg",
  flat: "text-ink-secondary",
};
const GLYPH: Record<TapeDirection, string | null> = { up: "▲", down: "▼", flat: null };
const SPOKEN: Record<TapeDirection, string> = { up: "up", down: "down", flat: "unchanged" };

function QuoteItem({ q }: { q: TapeQuote }) {
  const dir = tapeDirection(q);
  const change = formatTapeChange(q);
  const glyph = GLYPH[dir];
  return (
    <li className="flex shrink-0 items-baseline gap-2 whitespace-nowrap pr-8" title={q.name}>
      <span className="font-medium text-ink">{q.symbol}</span>
      <span className="text-ink">{formatTapePrice(q.price)}</span>
      {change ? (
        <span className={TONE[dir]}>
          {glyph ? (
            <span aria-hidden="true" className="mr-1">
              {glyph}
            </span>
          ) : null}
          <span className="sr-only">{SPOKEN[dir]} </span>
          {change}
        </span>
      ) : null}
    </li>
  );
}

export function TickerTape({ initial }: { initial: TickerTapePayload | null }) {
  const [data, setData] = useState<TickerTapePayload | null>(initial);
  const startedEmpty = !tapeVisible(initial);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    let last = 0;
    const refresh = async () => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      last = Date.now();
      try {
        const res = await fetch("/api/ticker-tape", { cache: "no-store" });
        const next = parseTickerTape(await res.json());
        if (!cancelled && next) setData(next);
      } catch {
        /* network hiccup: keep the last quotes */
      } finally {
        inFlight = false;
      }
    };
    // The server render waits only briefly for quotes; if it had none, try once right away.
    if (startedEmpty) void refresh();
    else last = Date.now();
    const timer = setInterval(() => void refresh(), REFRESH_MS);
    const onVisible = () => {
      if (!document.hidden && Date.now() - last >= REFRESH_MS) void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [startedEmpty]);

  if (!tapeVisible(data)) return null;

  const stale = data.status === "stale";
  const time = formatTapeTime(data.as_of, stale);
  const sourceLine = `Delayed quotes from ${data.source}${time ? `, ${stale ? "last updated" : "as of"} ${time}` : ""}`;
  const trackStyle = { "--tape-duration": `${tapeDurationSeconds(data.quotes.length)}s` } as CSSProperties;

  return (
    <section aria-label="Market prices" className="overflow-hidden border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1280px] items-center gap-6 px-8 py-2 text-sm">
        <p className="shrink-0 text-ink-secondary" title={sourceLine}>
          <span aria-hidden="true">Delayed prices</span>
          <span className="sr-only">{sourceLine}</span>
        </p>
        <div role="group" aria-label="Quotes" tabIndex={0} className="tape-viewport relative min-w-0 flex-1 focus-visible:[outline-offset:-3px]">
          <div className="tape-track" style={trackStyle}>
            <ul className="tape-copy flex">
              {data.quotes.map((q) => (
                <QuoteItem key={q.symbol} q={q} />
              ))}
            </ul>
            <ul className="tape-copy flex" aria-hidden="true" inert>
              {data.quotes.map((q) => (
                <QuoteItem key={q.symbol} q={q} />
              ))}
            </ul>
          </div>
        </div>
        {stale && time ? (
          <p aria-hidden="true" className="shrink-0 text-ink-secondary">
            Last updated {time}
          </p>
        ) : null}
      </div>
    </section>
  );
}
