/**
 * Shared presentational building blocks (no hooks: usable from server and client components).
 * Colors come from the design tokens through lib/vocabulary (DESIGN.md): badges and level
 * meters encode the DIRECTION of a disclosure change, never good or bad.
 */
import type { ReactNode } from "react";

import { FIXTURE_BANNER } from "@/lib/copy";
import {
  CHANGE_LEVEL,
  CHANGE_TONE,
  ACTUAL_TONE,
  changeLevel,
  changeTone,
  changeTypeVocab,
  highlightKindVocab,
  highlightTone,
  LEGEND,
  levelSegments,
  type Tone,
} from "@/lib/vocabulary";

// ---------------------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------------------

function Badge({ label, helper, tone, size, detail, ring = false }: { label: string; helper: string; tone: Tone; size: "sm" | "md"; detail?: string | null; ring?: boolean }) {
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-sm font-medium leading-none ${tone.bg} ${tone.text} ${
        size === "sm" ? "px-2 py-1 text-xs" : "px-2.5 py-1.5 text-sm"
      } ${ring ? "ring-1 ring-inset ring-actual-fg/60" : ""}`}
      title={helper || undefined}
    >
      <span className="whitespace-nowrap">{label}</span>
      {detail ? <span className="truncate font-normal">: {detail}</span> : null}
    </span>
  );
}

/**
 * The one change badge. Pass a change `type` (New risk, Expanded, Scaled back, Dropped risk,
 * Major update, Essentially unchanged) or a highlight `kind` (Potential became actual, New
 * figure disclosed / Figure changed, Newly named, New risk, Dropped risk).
 */
export function ChangeBadge({
  type,
  kind,
  figureChanged = false,
  size = "md",
  detail,
}: {
  type?: string;
  kind?: string;
  figureChanged?: boolean;
  size?: "sm" | "md";
  /** The named party or figure behind a highlight ("Groq", "$4.5 billion"). */
  detail?: string | null;
}) {
  if (kind) {
    const v = highlightKindVocab(kind, figureChanged);
    // Amber sits in the highlighter's family: the ring keeps "potential became actual" apart from "new words".
    return <Badge label={v.label} helper={v.helper} tone={highlightTone(kind)} size={size} detail={detail} ring={kind === "potential_became_actual"} />;
  }
  const v = changeTypeVocab(type ?? "largely_unchanged");
  return <Badge label={v.label} helper={v.helper} tone={changeTone(type ?? "largely_unchanged")} size={size} />;
}


// ---------------------------------------------------------------------------------------
// Change level: a 3-segment meter. Ink only: the fill is magnitude; direction lives in the badge
// beside it (two outside reviews read direction-colored segments as a severity gauge).
// ---------------------------------------------------------------------------------------

export function ChangeLevel({ score, changeType = "largely_unchanged", size = "md" }: { score: number; changeType?: string; size?: "sm" | "md" }) {
  const level = changeLevel(score);
  const filled = levelSegments(score);
  const title = `${score} of 100. ${CHANGE_LEVEL.helper}`;
  return (
    <span
      className={`inline-flex items-center gap-2 whitespace-nowrap ${size === "sm" ? "text-xs" : "text-sm"} text-ink-secondary`}
      title={title}
      aria-label={`${CHANGE_LEVEL.prefix}: ${level}, ${score} of 100`}
      data-change-type={changeType}
    >
      <span aria-hidden="true" className="inline-flex items-center gap-0.5">
        {[1, 2, 3].map((i) => (
          <span key={i} className={`block h-2.5 w-2.5 rounded-xs ${i <= filled ? "bg-ink" : "bg-line"}`} />
        ))}
      </span>
      <span aria-hidden="true">
        {CHANGE_LEVEL.prefix}: <span className="font-medium text-ink">{level}</span>
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------------------
// Legend: explains the three colors once
// ---------------------------------------------------------------------------------------

function Swatch({ tone }: { tone: Tone }) {
  return <span aria-hidden="true" className={`inline-block h-3 w-3 rounded-xs ${tone.fill}`} />;
}

export function Legend({ className = "" }: { className?: string }) {
  return (
    <p className={`flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-ink-secondary ${className}`} aria-label="Color legend">
      <span className="inline-flex items-center gap-2">
        <Swatch tone={CHANGE_TONE.new} /> Blue: {LEGEND.more}
      </span>
      <span className="inline-flex items-center gap-2">
        <Swatch tone={CHANGE_TONE.removed} /> Orange: {LEGEND.less}
      </span>
      <span className="inline-flex items-center gap-2">
        <Swatch tone={CHANGE_TONE.materially_reworded} /> Gray: {LEGEND.rewrite}
      </span>
      <span className="inline-flex items-center gap-2">
        <span aria-hidden="true" className={`inline-block h-3 w-3 rounded-xs ${ACTUAL_TONE.bg} ring-1 ring-inset ring-actual-fg/50`} /> Amber: {LEGEND.actual}
      </span>
      <span className="inline-flex items-center gap-2">
        <mark className="hl text-xs text-ink">new words</mark> Highlighter: new words this year
      </span>
    </p>
  );
}

// ---------------------------------------------------------------------------------------
// Layout helpers
// ---------------------------------------------------------------------------------------

export function PageContainer({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto max-w-[1280px] px-8 ${className}`}>{children}</div>;
}

/** Section heading: 22px, 500. Sections are separated by spacing and one rule, not boxes. */
export function SectionTitle({ id, children, aside }: { id?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-t border-line pt-6">
      <h2 id={id} className="text-lg font-medium text-ink">
        {children}
      </h2>
      {aside ? <div className="text-sm text-ink-secondary">{aside}</div> : null}
    </div>
  );
}

export function FixtureBanner() {
  return (
    <div role="note" aria-label="Fixture data warning" className="sticky top-14 z-30 border-y border-actual-fg/30 bg-actual-bg text-actual-fg">
      <div className="mx-auto flex h-10 max-w-[1280px] items-center gap-3 overflow-hidden px-8 text-sm">
        <strong className="font-medium">{FIXTURE_BANNER}</strong>
        <span>Hand-made development data. Company, filings, sentences and links are invented.</span>
      </div>
    </div>
  );
}

export function InfoBox({ title, children, tone = "info" }: { title?: string; children: ReactNode; tone?: "info" | "warn" }) {
  const toneClass = tone === "warn" ? "border-actual-fg bg-actual-bg text-actual-fg" : "border-ink bg-signal-bg text-ink";
  return (
    <div role="note" className={`rounded-md border-l-2 px-4 py-3 text-sm ${toneClass}`}>
      {title ? <p className="mb-1 font-medium">{title}</p> : null}
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="border-t border-line py-12 text-center">
      <p className="text-lg font-medium text-ink">{title}</p>
      {children ? <div className="mx-auto mt-2 max-w-[60ch] text-base text-ink-secondary">{children}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-sunken ${className}`} aria-hidden="true" />;
}

// ---------------------------------------------------------------------------------------
// Links
// ---------------------------------------------------------------------------------------

/** The only icon in the product: marks a link that leaves the site. */
export function ExternalIcon() {
  return (
    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" className="ml-1 inline-block align-[-1px]">
      <path d="M6 3H3.5A1.5 1.5 0 0 0 2 4.5v8A1.5 1.5 0 0 0 3.5 14h8a1.5 1.5 0 0 0 1.5-1.5V10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M9 2h5v5M14 2 7.5 8.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ExternalLink({ href, children, className = "" }: { href: string; children: ReactNode; className?: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`text-accent underline underline-offset-2 ${className}`}>
      {children}
      <ExternalIcon />
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export const FIXTURE_LINK_NOTE = "(fixture: no real filing)";

/**
 * Link to an SEC document. For FIXTURE comparisons the URL is invented, so it renders as
 * disabled text instead of a link to sec.gov. Only sec.gov URLs are ever linked.
 */
export function FilingLink({ href, isFixture, children, className = "" }: { href: string; isFixture: boolean; children: ReactNode; className?: string }) {
  if (isFixture) {
    return (
      <span aria-disabled="true" className={`cursor-not-allowed text-ink-muted ${className}`}>
        {children} <span className="font-normal">{FIXTURE_LINK_NOTE}</span>
      </span>
    );
  }
  if (!/^https:\/\/www\.sec\.gov\//.test(href)) {
    return (
      <span aria-disabled="true" className={`cursor-not-allowed text-ink-muted ${className}`}>
        {children} <span className="font-normal">(link outside sec.gov not shown)</span>
      </span>
    );
  }
  return (
    <ExternalLink href={href} className={className}>
      {children}
    </ExternalLink>
  );
}
