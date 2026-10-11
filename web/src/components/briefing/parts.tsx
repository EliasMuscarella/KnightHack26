/**
 * Shared pieces of the Disclosure Briefing document (server-safe, no hooks). Typography and print
 * rules live in briefing.css; colors come from the design tokens (DESIGN.md), re-declared light on
 * `.briefing` so the paper stays light in both themes.
 */
import type { ReactNode } from "react";

import { MarkedText, type MarkStatus } from "@/components/MarkedText";
import { FilingLink } from "@/components/ui";
import type { MarkedQuote, ReadFirstKind } from "@/lib/briefing/types";
import { ACTUAL_TONE, CHANGE_TONE, CHANGE_TYPE_VOCAB, SIGNAL_TONE, type Tone } from "@/lib/vocabulary";
import type { ChangeType } from "@/types/comparison";

// ---------------------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------------------

export function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

/** Signal values arrive as "may -> experienced"; the arrow is a data label, so it prints as "→". */
export function detailLabel(detail: string): string {
  return detail.replace(/\s*->\s*/g, " → ");
}

/** "a", "a and b", "a, b and c". */
export function joinAnd(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

// ---------------------------------------------------------------------------------------
// Page frame
// ---------------------------------------------------------------------------------------

/** One briefing page: the running header, then the page's content. Breaks before pages 2 to 4 in print. */
export function BriefingPage({ n, label, children }: { n: number; label: string; children: ReactNode }) {
  return (
    <section className="bf-page" data-page={n} aria-label={`Page ${n}: ${label}`}>
      <div className="bf-runhead">
        <span>
          <span className="bf-runhead-brand">RiskDiff</span>
          <span className="bf-runhead-name">Disclosure Briefing</span>
        </span>
        <span>{label}</span>
      </div>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// Badges (text always carries the meaning; color is the direction)
// ---------------------------------------------------------------------------------------

export function Pill({ tone, ring = false, children }: { tone: Tone; ring?: boolean; children: ReactNode }) {
  return (
    <span className={`bf-pill ${tone.bg} ${tone.text} ${ring ? "ring-1 ring-inset ring-actual-fg/60" : ""}`}>{children}</span>
  );
}

const READ_FIRST_BADGE: Record<ReadFirstKind, { label: string; tone: Tone; ring?: boolean }> = {
  potential_became_actual: { label: "Potential → Actual", tone: ACTUAL_TONE, ring: true },
  new_figure: { label: "New figure", tone: SIGNAL_TONE },
  new_risk: { label: "New risk", tone: CHANGE_TONE.new },
  removed_risk: { label: "Dropped risk", tone: CHANGE_TONE.removed },
  spreading: { label: "Spreading", tone: SIGNAL_TONE },
  quiet: { label: "Quiet", tone: SIGNAL_TONE },
};

export function ReadFirstBadge({ kind }: { kind: ReadFirstKind }) {
  const b = READ_FIRST_BADGE[kind] ?? { label: kind.replace(/_/g, " "), tone: SIGNAL_TONE };
  return (
    <Pill tone={b.tone} ring={b.ring}>
      {b.label}
    </Pill>
  );
}

export function ActualBadge() {
  return <ReadFirstBadge kind="potential_became_actual" />;
}

// ---------------------------------------------------------------------------------------
// Change mix (fixed order; fills from CHANGE_TONE)
// ---------------------------------------------------------------------------------------

export const MIX_ORDER: ChangeType[] = ["new", "expanded", "materially_reworded", "reduced", "removed", "largely_unchanged"];

/** Left rule color of a quote card, by the direction of its change. */
export const RULE_CLASS: Record<ChangeType, string> = {
  new: "border-more-strong-fg",
  expanded: "border-more-fg",
  materially_reworded: "border-rewrite-mid",
  reduced: "border-less-mid",
  removed: "border-less-strong-fg",
  largely_unchanged: "border-line",
};

export function changeLabel(t: ChangeType | null | undefined): string | null {
  return t ? (CHANGE_TYPE_VOCAB[t]?.label ?? null) : null;
}

/** A thin stacked bar of every risk factor by change type. The counts sit in the table and the label. */
export function MixBar({ mix, total }: { mix: Record<ChangeType, number>; total: number }) {
  const sum = MIX_ORDER.reduce((s, t) => s + (mix[t] ?? 0), 0) || total;
  const parts = MIX_ORDER.filter((t) => (mix[t] ?? 0) > 0);
  const label = parts.map((t) => `${mix[t]} ${CHANGE_TYPE_VOCAB[t].label.toLowerCase()}`).join(", ");
  return (
    <span className="bf-mix" role="img" aria-label={`Change mix: ${label || "no risk factors"}`}>
      {parts.map((t) => (
        <span
          key={t}
          className={`bf-mix-seg ${CHANGE_TONE[t].fill} ${t === "largely_unchanged" ? "is-faint" : ""}`}
          style={{ flexGrow: mix[t], flexBasis: 0 }}
          title={`${CHANGE_TYPE_VOCAB[t].label}: ${mix[t]} of ${sum}`}
        />
      ))}
    </span>
  );
}

export function MixLegend() {
  return (
    <p className="bf-legend" aria-label="Change mix legend">
      {MIX_ORDER.map((t) => (
        <span key={t} className="bf-legend-item">
          <span aria-hidden="true" className={`bf-swatch ${CHANGE_TONE[t].fill} ${t === "largely_unchanged" ? "is-faint" : ""}`} />
          {CHANGE_TYPE_VOCAB[t].label}
        </span>
      ))}
    </p>
  );
}

// ---------------------------------------------------------------------------------------
// Quotes and links
// ---------------------------------------------------------------------------------------

/** Status for MarkedText: word spans when the diff has them, else the whole sentence is new (or gone). */
function statusOf(q: MarkedQuote, side: "old" | "new"): MarkStatus {
  if (q.spans && q.spans.length > 0) return "modified";
  return side === "new" ? "added" : "removed";
}

/**
 * "View in the FY2025 10-K": the quote's deep link to exactly that sentence on sec.gov (a URL text
 * fragment, built in the model; see `sentenceSource` in lib/briefing/quotes.ts). Chromium keeps it as
 * a clickable link in the PDF. It sits on the line right above its quote (the card head or the
 * "Last year" / "This year" label), so it costs no extra line. Fixtures print as disabled text; a
 * quote with no link prints nothing.
 */
export function QuoteLink({ quote, isFixture }: { quote: MarkedQuote | null; isFixture: boolean }) {
  if (!quote || (!quote.href && !isFixture)) return null;
  const label = quote.fiscalYear ? `View in the FY${quote.fiscalYear} 10-K` : "View in the 10-K";
  return (
    <SecLink href={quote.href ?? ""} isFixture={isFixture} compact>
      {label}
    </SecLink>
  );
}

/**
 * A verbatim filing sentence in the serif, printed in full (no trimming, no controls: this is
 * paper). The marks come from the deterministic diff only.
 */
export function FilingQuote({ quote, side, status }: { quote: MarkedQuote; side: "old" | "new"; status?: MarkStatus }) {
  return (
    <blockquote className={`bf-quote ${side === "old" ? "is-old" : "is-new"}`}>
      <MarkedText text={quote.text} spans={quote.spans} side={side} status={status ?? statusOf(quote, side)} />
    </blockquote>
  );
}

/**
 * A link to an SEC document. FilingLink renders fixture and non-sec.gov URLs as disabled text; next
 * to a quote or in a table cell its long fixture note would crowd the line, so `compact` shortens it.
 */
export function SecLink({
  href,
  isFixture,
  compact = false,
  children = "SEC filing",
}: {
  href: string;
  isFixture: boolean;
  compact?: boolean;
  children?: ReactNode;
}) {
  if (compact && isFixture) {
    return (
      <span aria-disabled="true" className="bf-fixturelink">
        {children} <span className="font-normal">(fixture)</span>
      </span>
    );
  }
  return (
    <FilingLink href={href} isFixture={isFixture} className="bf-seclink">
      {children}
    </FilingLink>
  );
}

/** Company + title on the left; on the right, the link to the single quote below (QuoteLink), if any. */
export function EvidenceHead({ name, sub, link = null }: { name: string; sub: ReactNode; link?: ReactNode }) {
  return (
    <div className="bf-evhead">
      <p>
        <span className="bf-strong">{name}</span>
        {sub ? <span className="bf-secondary"> {sub}</span> : null}
      </p>
      {link ? <span className="bf-evlink">{link}</span> : null}
    </div>
  );
}

/**
 * "Last year" (muted, strikes) beside "This year" (ink, highlighter). Either side may be absent.
 * Each side links into its own filing: last year's sentence into the old 10-K, this year's into the new.
 */
export function BeforeAfter({ old, now, isFixture }: { old: MarkedQuote | null; now: MarkedQuote | null; isFixture: boolean }) {
  return (
    <div className="bf-pair-cols">
      <div>
        <p className="bf-collabel">
          <span>Last year</span>
          <QuoteLink quote={old} isFixture={isFixture} />
        </p>
        {old ? <FilingQuote quote={old} side="old" /> : <p className="bf-secondary">Not in last year&apos;s filing.</p>}
      </div>
      <div>
        <p className="bf-collabel">
          <span>This year</span>
          <QuoteLink quote={now} isFixture={isFixture} />
        </p>
        {now ? <FilingQuote quote={now} side="new" /> : <p className="bf-secondary">Not in this year&apos;s filing.</p>}
      </div>
    </div>
  );
}

export function Dot({ on }: { on: boolean }) {
  return on ? (
    <>
      <span aria-hidden="true" className="bf-dot" />
      <span className="sr-only">yes</span>
    </>
  ) : (
    <span className="sr-only">no</span>
  );
}
