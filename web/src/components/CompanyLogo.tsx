import Image from "next/image";

import { logoFor } from "@/lib/logos";
import { TICKER_PATTERN } from "@/lib/ticker";

type Size = "sm" | "md" | "lg";

/** Tile height in px; marks are square, wordmarks get a 3:1 tile. */
const HEIGHT: Record<Size, number> = { sm: 32, md: 40, lg: 56 };
const PADDING: Record<Size, number> = { sm: 5, md: 6, lg: 9 };

/**
 * A company's bundled logo on a light rounded tile, or a ticker monogram when no logo is bundled.
 *
 * The logo tile is deliberately white in every theme: brand marks are drawn for a light background
 * (black Apple, black NVIDIA type), so the tile keeps them legible under a dark theme, the way a
 * printed logo sits on its own paper. The monogram uses theme tokens only.
 */
export function CompanyLogo({
  ticker,
  name,
  size = "md",
  className = "",
}: {
  ticker: string;
  name?: string;
  size?: Size;
  className?: string;
}) {
  const upper = typeof ticker === "string" ? ticker.trim().toUpperCase() : "";
  const valid = TICKER_PATTERN.test(upper);
  const logo = valid ? logoFor(upper) : null;
  const height = HEIGHT[size];

  if (logo) {
    const width = logo.shape === "wordmark" ? height * 3 : height;
    const pad = PADDING[size];
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-md border border-line bg-white ${className}`}
        style={{ width, height, padding: pad }}
      >
        <Image
          src={logo.src}
          alt={`${name?.trim() || upper} logo`}
          width={width - pad * 2}
          height={height - pad * 2}
          unoptimized
          className="h-full w-full object-contain"
        />
      </span>
    );
  }

  // Monogram: decorative, the ticker is always printed next to it as text.
  const label = valid ? upper : "?";
  const text = size === "lg" ? "text-sm" : "text-xs";
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-md border border-line bg-sunken px-1.5 font-medium tabular-nums tracking-tight text-ink ${text} ${className}`}
      style={{ minWidth: height, height }}
    >
      {label}
    </span>
  );
}
