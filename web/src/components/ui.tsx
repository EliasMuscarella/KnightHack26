/** Small presentational building blocks (no hooks: usable from server and client components). */
import type { ReactNode } from "react";

import { categoryLabel, changeTypeMeta } from "@/lib/format";
import { FIXTURE_BANNER, SCORE_EXPLAINER } from "@/lib/copy";

export function ChangeTypeBadge({ type, size = "md" }: { type: string; size?: "sm" | "md" }) {
  const meta = changeTypeMeta(type);
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded border font-semibold ${meta.badgeClass} ${
        size === "sm" ? "px-1.5 py-px text-xs" : "px-2 py-0.5 text-sm"
      }`}
      title={meta.description}
    >
      <span aria-hidden="true" className="font-mono">
        {meta.marker}
      </span>
      {meta.label}
    </span>
  );
}

export function CategoryChip({ category }: { category: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line bg-sunken px-2 py-px text-xs font-medium text-ink-muted">
      {categoryLabel(category)}
    </span>
  );
}

export function ScoreBar({ score, width = "w-20", showLabel = true }: { score: number; width?: string; showLabel?: boolean }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <span className="inline-flex items-center gap-2" title={SCORE_EXPLAINER}>
      {showLabel ? (
        <span className="w-8 text-right font-mono text-sm font-semibold tabular-nums text-ink">{score}</span>
      ) : null}
      <span
        className={`relative h-2 ${width} overflow-hidden rounded-full border border-line-strong bg-surface`}
        role="meter"
        aria-label="Change score"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
      >
        <span className="absolute inset-y-0 left-0 bg-ink-muted" style={{ width: `${clamped}%` }} />
      </span>
    </span>
  );
}

export function FixtureBanner() {
  return (
    <div
      role="note"
      aria-label="Fixture data warning"
      className="sticky top-14 z-30 border-y-2 border-fixture-line bg-fixture-bg text-fixture-fg"
    >
      <div className="mx-auto flex h-10 max-w-[1400px] items-center gap-3 overflow-hidden px-8 text-sm">
        <span aria-hidden="true" className="font-mono text-base font-bold">
          ⚠
        </span>
        <strong className="tracking-wide">{FIXTURE_BANNER}</strong>
        <span className="text-fixture-fg/90">
          Hand-made development data used to build and demo the interface. Company, filings, sentences and links are
          invented.
        </span>
      </div>
    </div>
  );
}

export function InfoBox({ title, children, tone = "info" }: { title?: string; children: ReactNode; tone?: "info" | "warn" }) {
  const toneClass =
    tone === "warn" ? "border-mod-line bg-mod-bg text-mod-fg" : "border-accent/40 bg-accent-bg text-accent-strong";
  return (
    <div role="note" className={`rounded-md border-l-4 px-4 py-3 text-sm ${toneClass}`}>
      {title ? (
        <p className="mb-1 font-semibold">
          <span aria-hidden="true">{tone === "warn" ? "! " : "ⓘ "}</span>
          {title}
        </p>
      ) : null}
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

export function PageContainer({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto max-w-[1400px] px-8 ${className}`}>{children}</div>;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong bg-surface px-8 py-12 text-center">
      <p className="text-lg font-semibold text-ink">{title}</p>
      {children ? <div className="mx-auto mt-2 max-w-[65ch] text-ink-muted">{children}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-sunken ${className}`} aria-hidden="true" />;
}

export function ExternalLink({ href, children, className = "" }: { href: string; children: ReactNode; className?: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent ${className}`}
    >
      {children}
      <span aria-hidden="true"> ↗</span>
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export const FIXTURE_LINK_NOTE = "(fixture: no real filing)";

/**
 * Link to an SEC document. For FIXTURE comparisons the URL is invented, so it renders as
 * disabled text instead of a link to sec.gov.
 */
export function FilingLink({
  href,
  isFixture,
  children,
  className = "",
}: {
  href: string;
  isFixture: boolean;
  children: ReactNode;
  className?: string;
}) {
  if (isFixture) {
    return (
      <span aria-disabled="true" className={`cursor-not-allowed text-ink-faint ${className}`}>
        {children} <span className="font-normal italic">{FIXTURE_LINK_NOTE}</span>
      </span>
    );
  }
  // Filing links may only point at sec.gov; anything else (from an untrusted API payload) is not linked.
  if (!/^https:\/\/www\.sec\.gov\//.test(href)) {
    return (
      <span aria-disabled="true" className={`cursor-not-allowed text-ink-faint ${className}`}>
        {children} <span className="font-normal italic">(link outside sec.gov not shown)</span>
      </span>
    );
  }
  return (
    <ExternalLink href={href} className={className}>
      {children}
    </ExternalLink>
  );
}
