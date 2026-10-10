import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import type { Change } from "@/types/comparison";

import { ChangeDetail } from "@/components/ChangeDetail";
import type { SentenceRef } from "@/components/citations";
import { ChangeBadge, ChangeLevel, FixtureBanner, PageContainer } from "@/components/ui";
import { getComparison } from "@/lib/data";
import { displayName } from "@/lib/names";
import { CHANGE_ID_RE, normalizeTicker } from "@/lib/ticker";
import { displayTitle } from "@/lib/vocabulary";

export const dynamic = "force-dynamic";

async function load(props: PageProps<"/c/[ticker]/[changeId]">) {
  const { ticker: rawTicker, changeId } = await props.params;
  const ticker = normalizeTicker(rawTicker);
  if (!ticker || !CHANGE_ID_RE.test(changeId)) return null;
  const result = await getComparison(ticker);
  if (!result) return null;
  const idx = result.comparison.changes.findIndex((c) => c.id === changeId);
  if (idx === -1) return null;
  return { ...result, idx, change: result.comparison.changes[idx] };
}

export async function generateMetadata(props: PageProps<"/c/[ticker]/[changeId]">): Promise<Metadata> {
  const data = await load(props);
  return { title: data ? `${displayName(data.comparison.company.name)}: ${displayTitle(data.change.short_title, data.change.title)}` : "Change" };
}

function NavLink({ ticker, change, dir }: { ticker: string; change: Change | undefined; dir: "prev" | "next" }) {
  if (!change) {
    return (
      <span className={`min-w-0 flex-1 py-3 text-sm text-ink-secondary ${dir === "next" ? "text-right" : ""}`}>
        {dir === "prev" ? "This is the top-ranked risk factor." : "This is the lowest-ranked risk factor."}
      </span>
    );
  }
  return (
    <Link
      href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(change.id)}`}
      className={`group min-w-0 flex-1 py-3 ${dir === "next" ? "text-right" : ""}`}
    >
      <span className="block text-sm text-ink-secondary">{dir === "prev" ? "Previous risk factor" : "Next risk factor"}</span>
      <span className="mt-0.5 line-clamp-2 text-base font-medium leading-snug text-ink group-hover:underline" title={change.title}>
        {displayTitle(change.short_title, change.title)}
      </span>
    </Link>
  );
}

export default async function ChangePage(props: PageProps<"/c/[ticker]/[changeId]">) {
  const data = await load(props);
  if (!data) notFound();
  const { comparison, change, idx } = data;
  const ticker = comparison.company.ticker;
  const company = displayName(comparison.company.name);
  const prev = comparison.changes[idx - 1];
  const next = comparison.changes[idx + 1];

  // Only ship the sentence_index entries this change references.
  const wanted = new Set<string>(change.sentences.map((s) => s.id));
  for (const l of change.score_breakdown) l.cited_sentence_ids.forEach((id) => wanted.add(id));
  for (const c of change.interpretation.claims ?? []) c.cited_sentence_ids.forEach((id) => wanted.add(id));
  for (const r of change.interpretation.rubric ?? []) (r.cited_sentence_ids ?? []).forEach((id) => wanted.add(id));
  for (const hits of [change.signals.hypothetical_to_actual, change.signals.new_entities, change.signals.new_quantities]) {
    for (const h of hits ?? []) [...(h.old_sentence_ids ?? []), ...(h.new_sentence_ids ?? [])].forEach((id) => wanted.add(id));
  }
  const index: Record<string, SentenceRef> = {};
  for (const id of wanted) {
    const loc = comparison.sentence_index[id];
    if (loc) index[id] = { id, side: loc.side, text: loc.text, is_heading: loc.is_heading === true };
  }
  const filingRef = (f: typeof comparison.old_filing) => ({
    fiscal_year: f.fiscal_year,
    form: f.form,
    edgar_url: f.edgar_url,
    filing_date: f.filing_date,
  });
  const oldTitle = change.old_title ?? null;
  const newTitle = change.new_title ?? null;
  const titlesDiffer = !!oldTitle && !!newTitle && oldTitle !== newTitle;
  const heading = displayTitle(change.short_title, change.title);
  const bare = (t: string) => t.trim().replace(/[.…\s]+$/, "");
  const showFullTitle = !!change.title && bare(change.title) !== bare(heading);

  return (
    <>
      {comparison.is_fixture ? <FixtureBanner /> : null}
      <PageContainer className="space-y-10 py-10">
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center justify-between gap-2 text-sm text-ink-secondary">
          <span>
            <Link href={`/c/${encodeURIComponent(ticker)}`} className="underline hover:text-ink">
              {company}
            </Link>
            <span aria-hidden="true"> / </span>
            <span className="text-ink">
              Risk factor {change.rank} of {comparison.changes.length}, ranked by how much the wording changed
            </span>
          </span>
          <Link href={`/c/${encodeURIComponent(ticker)}`} className="underline hover:text-ink">
            All {comparison.changes.length} risk factors
          </Link>
        </nav>

        <header className="max-w-[90ch]">
          <h1 className="text-xl font-title leading-tight tracking-tight text-ink">{heading}</h1>
          {titlesDiffer || showFullTitle ? (
            <div className="mt-3 space-y-1 text-base leading-snug text-ink-secondary">
              {titlesDiffer ? (
                <>
                  <p>Last year: {oldTitle}</p>
                  <p>This year: {newTitle}</p>
                </>
              ) : (
                <p>{change.title}</p>
              )}
            </div>
          ) : null}
          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2">
            <ChangeBadge type={change.change_type} />
            <ChangeLevel score={change.score} changeType={change.change_type} />
            <span className="text-sm text-ink-secondary">
              {change.stats.old_word_count.toLocaleString("en-US")} words last year, {change.stats.new_word_count.toLocaleString("en-US")} this year
            </span>
          </div>
        </header>

        <ChangeDetail
          change={change}
          index={index}
          filings={{ old: filingRef(comparison.old_filing), new: filingRef(comparison.new_filing) }}
          isFixture={comparison.is_fixture === true}
          modelIds={comparison.model_ids}
        />

        <nav aria-label="Other risk factors" className="flex gap-8 border-t border-line">
          <NavLink ticker={ticker} change={prev} dir="prev" />
          <NavLink ticker={ticker} change={next} dir="next" />
        </nav>
      </PageContainer>
    </>
  );
}
