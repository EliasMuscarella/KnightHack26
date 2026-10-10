/**
 * The before/after card (DESIGN.md): the badge, a 22px short title, one quiet source line, then
 * "Last year" (muted serif, removed words struck) beside "This year" (ink serif, the highlighter
 * on changed words). Used on the company page, the home hero and Trends. Server component.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import type { Change, Comparison, Highlight } from "@/types/comparison";

import { Quote } from "@/components/Quote";
import { ChangeBadge, FilingLink } from "@/components/ui";
import { textFragmentUrl } from "@/lib/format";
import { displayName } from "@/lib/names";
import { quoteSource } from "@/lib/sentences";
import { changeTypeVocab, displayTitle, factDetail, highlightKindVocab, isFigureChanged } from "@/lib/vocabulary";

export { factDetail };

export interface FactProps {
  h: Highlight;
  change: Change;
  comparison: Comparison;
  /** Hide the badge when the card header already shows it. */
  withBadge?: boolean;
}

/** Kind-aware caption for an empty side: a new name or figure does not make the whole risk new. */
export function absentCaptions(h: Pick<Highlight, "kind">): { absentOld: string; absentNew: string } {
  const absentOld =
    h.kind === "new_risk"
      ? "Not in last year's filing"
      : h.kind === "new_named_party"
        ? "This name did not appear last year"
        : h.kind === "new_figure"
          ? "This figure did not appear last year"
          : "No matching sentence last year";
  const absentNew = h.kind === "removed_risk" ? "Removed this year" : "No matching sentence this year";
  return { absentOld, absentNew };
}

export function BeforeAfter({
  oldText,
  newText,
  absentOld,
  absentNew,
  oldFY,
  newFY,
}: {
  oldText: { text: string; status: "added" | "removed" | "modified" | "unchanged"; spans: Change["sentences"][number]["diff_spans"] | null } | null;
  newText: { text: string; status: "added" | "removed" | "modified" | "unchanged"; spans: Change["sentences"][number]["diff_spans"] | null } | null;
  absentOld: string;
  absentNew: string;
  oldFY: number;
  newFY: number;
}) {
  return (
    <div className="grid gap-x-10 gap-y-4 min-[900px]:grid-cols-2">
      <div className="min-w-0">
        <p className="mb-1.5 text-sm text-ink-secondary">Last year, FY{oldFY}</p>
        {oldText ? <Quote text={oldText.text} side="old" status={oldText.status} spans={oldText.spans} /> : <p className="text-base text-ink-muted">{absentOld}</p>}
      </div>
      <div className="min-w-0">
        <p className="mb-1.5 text-sm text-ink-secondary">This year, FY{newFY}</p>
        {newText ? <Quote text={newText.text} side="new" status={newText.status} spans={newText.spans} /> : <p className="text-base text-ink-muted">{absentNew}</p>}
      </div>
    </div>
  );
}

export function Fact({ h, change, comparison, withBadge = true }: FactProps) {
  const oldQ = quoteSource(comparison, change, h.old_sentence_id);
  const newQ = quoteSource(comparison, change, h.new_sentence_id);
  const { absentOld, absentNew } = absentCaptions(h);
  return (
    <div>
      {withBadge ? (
        <div className="mb-3">
          <ChangeBadge kind={h.kind} figureChanged={isFigureChanged(h)} detail={factDetail(h)} />
        </div>
      ) : null}
      <BeforeAfter
        oldText={oldQ}
        newText={newQ}
        absentOld={absentOld}
        absentNew={absentNew}
        oldFY={comparison.old_filing.fiscal_year}
        newFY={comparison.new_filing.fiscal_year}
      />
    </div>
  );
}

export interface HighlightCardProps {
  change: Change;
  facts: Highlight[];
  comparison: Comparison;
  /** "card": a bordered card (clickable context). "plain": no border, for the home hero. */
  variant?: "card" | "plain";
  /** Line under the title (risk factor, company, fiscal years). `null` hides it, for pages that already say so. */
  source?: ReactNode | null;
  showCompany?: boolean;
  id?: string;
}

export function HighlightCard({ change, facts, comparison, variant = "card", source, showCompany = false, id }: HighlightCardProps) {
  const idx = comparison.sentence_index;
  const ticker = comparison.company.ticker;
  const first = facts[0];
  const textOf = (sid: string | null | undefined) => (sid ? (idx[sid]?.text ?? null) : null);
  const newLink = facts.map((h) => textOf(h.new_sentence_id)).find((t): t is string => t !== null) ?? null;
  const oldLink = facts.map((h) => textOf(h.old_sentence_id)).find((t): t is string => t !== null) ?? null;
  const linkText = newLink ?? oldLink;
  const filing = newLink !== null ? comparison.new_filing : comparison.old_filing;
  const title = displayTitle(change.short_title, change.title);
  const company = displayName(comparison.company.name);
  // "New risk" as the change type and "New risk" as the fact would show the same badge twice.
  const factBadge = first && highlightKindVocab(first.kind, isFigureChanged(first)).label !== changeTypeVocab(change.change_type).label;
  return (
    <article id={id} className={variant === "card" ? "border-t border-line pt-6" : ""}>
      <div className="flex flex-wrap items-center gap-3">
        <ChangeBadge type={change.change_type} />
        {first && factBadge ? <ChangeBadge kind={first.kind} figureChanged={isFigureChanged(first)} detail={factDetail(first)} /> : null}
        {showCompany ? (
          <Link href={`/c/${encodeURIComponent(ticker)}`} className="text-sm text-ink-secondary underline-offset-2 hover:underline">
            {company}
          </Link>
        ) : null}
      </div>
      <h3 className="mt-3 text-lg font-medium leading-snug text-ink">{title}</h3>
      {source === null ? null : (
        <p className="mt-1 text-sm text-ink-secondary">
          {source ?? (
            <>
              Risk factor in {company}&apos;s annual reports, FY{comparison.old_filing.fiscal_year} and FY{comparison.new_filing.fiscal_year}
            </>
          )}
        </p>
      )}
      <div className="mt-6 space-y-6">
        {facts.map((h, i) => (
          <div key={i} className={i > 0 ? "border-t border-line pt-6" : ""}>
            <Fact h={h} change={change} comparison={comparison} withBadge={i > 0} />
          </div>
        ))}
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
        {linkText !== null ? (
          <FilingLink href={textFragmentUrl(filing.edgar_url, linkText)} isFixture={comparison.is_fixture === true}>
            Open in SEC filing
          </FilingLink>
        ) : null}
        <Link href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(change.id)}`} className="text-accent underline underline-offset-2">
          See the full change
        </Link>
      </div>
    </article>
  );
}

/** Highlights grouped by risk factor, in order of first appearance. */
export function groupHighlights(comparison: Comparison): { change: Change; facts: Highlight[] }[] {
  const byId = new Map(comparison.changes.map((c) => [c.id, c] as const));
  const groups: { change: Change; facts: Highlight[] }[] = [];
  const groupOf = new Map<string, { change: Change; facts: Highlight[] }>();
  for (const h of comparison.highlights ?? []) {
    const change = byId.get(h.change_id);
    if (!change) continue;
    let g = groupOf.get(h.change_id);
    if (!g) {
      g = { change, facts: [] };
      groupOf.set(h.change_id, g);
      groups.push(g);
    }
    g.facts.push(h);
  }
  return groups;
}
