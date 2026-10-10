import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import type { Change } from "@/types/comparison";

import { ChangeDetail } from "@/components/ChangeDetail";
import type { SentenceRef } from "@/components/citations";
import { ChangeLevelTag, ChangeTypeBadge, FixtureBanner, PageContainer } from "@/components/ui";
import { getComparison } from "@/lib/data";
import { CHANGE_LEVEL } from "@/lib/vocabulary";
import { CHANGE_ID_RE, normalizeTicker } from "@/lib/ticker";

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
  return { title: data ? `${data.comparison.company.ticker}: ${data.change.short_title || data.change.title}` : "Change" };
}

function NavLink({ ticker, change, dir }: { ticker: string; change: Change | undefined; dir: "prev" | "next" }) {
  if (!change) {
    return (
      <span className="min-w-0 flex-1 rounded-md border border-dashed border-line px-4 py-3 text-sm text-ink-faint">
        {dir === "prev" ? "This is the first change." : "This is the last change."}
      </span>
    );
  }
  return (
    <Link
      href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(change.id)}`}
      className={`group min-w-0 flex-1 rounded-md border border-line bg-surface px-4 py-3 hover:border-accent ${dir === "next" ? "text-right" : ""}`}
    >
      <span className="block text-xs font-semibold uppercase tracking-wide text-ink-faint">
        {dir === "prev" ? "← Previous change" : "Next change →"}
      </span>
      <span className="mt-0.5 block truncate text-base font-medium text-ink group-hover:underline">{change.short_title || change.title}</span>
    </Link>
  );
}

export default async function ChangePage(props: PageProps<"/c/[ticker]/[changeId]">) {
  const data = await load(props);
  if (!data) notFound();
  const { comparison, change, idx } = data;
  const ticker = comparison.company.ticker;
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

  return (
    <>
      {comparison.is_fixture ? <FixtureBanner /> : null}
      <PageContainer className="space-y-8 py-7">
        <nav aria-label="Breadcrumb" className="flex items-center justify-between text-sm text-ink-faint">
          <span>
            <Link href="/" className="underline hover:text-ink">
              Home
            </Link>{" "}
            <span aria-hidden="true">/</span>{" "}
            <Link href={`/c/${encodeURIComponent(ticker)}`} className="underline hover:text-ink">
              {comparison.company.name}
            </Link>{" "}
            <span aria-hidden="true">/</span> <span className="text-ink">Change {change.rank} of {comparison.changes.length}</span>
          </span>
          <Link href={`/c/${encodeURIComponent(ticker)}`} className="font-medium text-accent underline">
            ← All {comparison.changes.length} risk factors
          </Link>
        </nav>

        <header className="rounded-lg border border-line bg-surface p-6">
          <h1 className="text-3xl font-bold leading-tight tracking-tight text-ink">{change.short_title || change.title}</h1>
          <div className="mt-2 max-w-[100ch] space-y-1 text-base leading-snug text-ink-faint">
            {titlesDiffer ? (
              <>
                <p>
                  <span className="font-semibold text-ink-muted">Last year:</span> {oldTitle}
                </p>
                <p>
                  <span className="font-semibold text-ink-muted">This year:</span> {newTitle}
                </p>
              </>
            ) : (
              <p>{change.title}</p>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
            <ChangeTypeBadge type={change.change_type} />
            <span className="inline-flex items-center gap-2">
              <span className="text-sm text-ink-faint">{CHANGE_LEVEL.label}</span>
              <ChangeLevelTag score={change.score} />
            </span>
            <span className="text-sm text-ink-muted">
              <span className="text-ink-faint">Words, last year → this year:</span>{" "}
              <span className="font-semibold tabular-nums text-ink">
                {change.stats.old_word_count.toLocaleString("en-US")} <span aria-hidden="true">→</span>
                <span className="sr-only">to</span> {change.stats.new_word_count.toLocaleString("en-US")}
              </span>
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

        <nav aria-label="Other changes" className="flex gap-4">
          <NavLink ticker={ticker} change={prev} dir="prev" />
          <NavLink ticker={ticker} change={next} dir="next" />
        </nav>
      </PageContainer>
    </>
  );
}
