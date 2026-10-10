/**
 * Bundled company logos (web/public/logos/{TICKER}.svg, sources in web/public/logos/SOURCES.md).
 * Only tickers listed here get an image request, so a missing logo never causes a 404; every other
 * ticker renders the monogram badge. Logos are served from /logos/ only, never from an external URL.
 */
import { TICKER_PATTERN } from "@/lib/ticker";

/** "mark": roughly square symbol. "wordmark": a wide logotype that needs a wider tile. */
export type LogoShape = "mark" | "wordmark";

const LOGO_MANIFEST = {
  AAPL: "mark",
  AMZN: "mark",
  CRWD: "wordmark",
  NVDA: "wordmark",
  SF: "wordmark",
} as const satisfies Record<string, LogoShape>;

export type LogoTicker = keyof typeof LOGO_MANIFEST;

export interface BundledLogo {
  src: string;
  shape: LogoShape;
}

function hasLogo(ticker: string): ticker is LogoTicker {
  return Object.prototype.hasOwnProperty.call(LOGO_MANIFEST, ticker);
}

/** The bundled logo for a ticker, or null. The ticker is validated before any path is built. */
export function logoFor(ticker: string): BundledLogo | null {
  const upper = typeof ticker === "string" ? ticker.trim().toUpperCase() : "";
  if (!TICKER_PATTERN.test(upper) || !hasLogo(upper)) return null;
  return { src: `/logos/${upper}.svg`, shape: LOGO_MANIFEST[upper] };
}
