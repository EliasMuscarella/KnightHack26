import Image from "next/image";

import { logoFor, type LogoShape } from "@/lib/logos";
import { TICKER_PATTERN } from "@/lib/ticker";

type Size = "sm" | "md" | "lg";

/**
 * One tile per size step for every company: square marks, wide wordmarks and the monogram all
 * share it, so the company name next to the tile starts at the same x on every card and header.
 * 1.75:1 keeps square marks from floating in a long empty box while leaving wordmarks wide enough
 * to read (D-034).
 */
const TILE: Record<Size, { width: number; height: number }> = {
  sm: { width: 70, height: 40 },
  md: { width: 91, height: 52 },
  lg: { width: 112, height: 64 },
};

/** Inner padding [vertical, horizontal] in px: marks sit centered with air around them; wordmarks
 * use more of the height and are scaled down to the tile width. */
const PADDING: Record<Size, Record<LogoShape, [number, number]>> = {
  sm: { mark: [7, 7], wordmark: [4, 5] },
  md: { mark: [9, 9], wordmark: [6, 6] },
  lg: { mark: [11, 11], wordmark: [7, 8] },
};

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
  const { width, height } = TILE[size];

  if (logo) {
    const [padY, padX] = PADDING[size][logo.shape];
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-md border border-line bg-white ${className}`}
        style={{ width, height, padding: `${padY}px ${padX}px` }}
      >
        <Image
          src={logo.src}
          alt={`${name?.trim() || upper} logo`}
          width={width - padX * 2}
          height={height - padY * 2}
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
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-md border border-line bg-sunken px-1 font-medium tabular-nums tracking-tight text-ink ${text} ${className}`}
      style={{ width, height }}
    >
      {label}
    </span>
  );
}
