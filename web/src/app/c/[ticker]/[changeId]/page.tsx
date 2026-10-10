import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import type { Change } from "@/types/comparison";

import { ChangeDetail } from "@/components/ChangeDetail";
import type { SentenceRef } from "@/components/citations";
import { CategoryChip, ChangeTypeBadge, FixtureBanner, PageContainer, ScoreBar } from "@/components/ui";
import { getComparison } from "@/lib/data";
import { formatRatio } from "@/lib/format";
import { normalizeTicker } from "@/lib/ticker";

export const dynamic = "force-dynamic";

const CHANGE_ID_RE = /^[A-Za-z0-9_\-]{1,128}$/;

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
  return { title: data ? `${data.comparison.company.ticker}: ${data.change.title}` : "Change" };
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
        {dir === "prev" ? "← Previous" : "Next →"} · #{change.rank}
      </span>
      <span className="mt-0.5 block truncate text-sm font-medium text-ink group-hover:underline">{change.title}</span>
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
  const titleChanged = change.old_title && change.new_title && change.old_title !== change.new_title;

  return (
    <>
      {comparison.is_fixture ? <FixtureBanner /> : null}
      <PageContainer className="space-y-6 py-8">
        <nav aria-label="Breadcrumb" className="flex items-center justify-between text-sm text-ink-faint">
          <span>
            <Link href="/" className="underline hover:text-ink">
              Home
            </Link>{" "}
            <span aria-hidden="true">/</span>{" "}
            <Link href={`/c/${encodeURIComponent(ticker)}`} className="font-mono underline hover:text-ink">
              {ticker}
            </Link>{" "}
            <span aria-hidden="true">/</span> <span className="text-ink">Change #{change.rank}</span>
          </span>
          <Link href={`/c/${encodeURIComponent(ticker)}`} className="font-medium text-accent underline">
            ← Back to all {comparison.changes.length} changes
          </Link>
        </nav>

        <header className="rounded-lg border border-line bg-surface p-6">
          <div className="flex items-start justify-between gap-8">
            <div className="min-w-0 max-w-[90ch]">
              <p className="text-sm text-ink-faint">
                <span className="font-mono font-semibold">#{change.rank}</span> of {comparison.changes.length} ·{" "}
                {comparison.company.name}
              </p>
              <h1 className="mt-1 text-2xl font-bold leading-snug tracking-tight text-ink">{change.title}</h1>
              {titleChanged ? (
                <p className="mt-2 text-sm text-ink-muted">
                  <span className="font-semibold">FY{comparison.old_filing.fiscal_year} heading:</span>{" "}
                  <span className="line-through decoration-del-line">{change.old_title}</span>
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <ChangeTypeBadge type={change.change_type} />
                {change.categories.map((c) => (
                  <CategoryChip key={c} category={c} />
                ))}
                {change.section_group ? <span className="text-sm text-ink-faint">· {change.section_group}</span> : null}
              </div>
            </div>
            <dl className="grid shrink-0 grid-cols-[auto_auto] items-center gap-x-4 gap-y-2 text-sm">
              <dt className="text-ink-faint">Change score</dt>
              <dd>
                <ScoreBar score={change.score} width="w-28" />
              </dd>
              <dt className="text-ink-faint">Match similarity</dt>
              <dd className="font-mono tabular-nums text-ink">
                {change.similarity === null || change.similarity === undefined ? (
                  <span className="font-sans text-ink-faint">n/a (unmatched)</span>
                ) : (
                  formatRatio(change.similarity)
                )}
              </dd>
              {change.heading_similarity != null || change.body_similarity != null ? (
                <>
                  <dt className="text-ink-faint">Heading / body</dt>
                  <dd className="font-mono tabular-nums text-ink">
                    {formatRatio(change.heading_similarity)} / {formatRatio(change.body_similarity)}
                  </dd>
                </>
              ) : null}
              <dt className="text-ink-faint">Sentences</dt>
              <dd className="flex gap-3 font-mono tabular-nums">
                <span className="text-add-fg">+{change.stats.added}<span className="sr-only"> added</span></span>
                <span className="text-del-fg">−{change.stats.removed}<span className="sr-only"> removed</span></span>
                <span className="text-mod-fg">~{change.stats.modified}<span className="sr-only"> modified</span></span>
                <span className="text-ink-faint">={change.stats.unchanged}<span className="sr-only"> unchanged</span></span>
              </dd>
              <dt className="text-ink-faint">Words</dt>
              <dd className="font-mono tabular-nums text-ink">
                {change.stats.old_word_count} → {change.stats.new_word_count}
              </dd>
            </dl>
          </div>
        </header>

        <ChangeDetail
          change={change}
          index={index}
          filings={{ old: filingRef(comparison.old_filing), new: filingRef(comparison.new_filing) }}
          isFixture={comparison.is_fixture === true}
        />

        <nav aria-label="Other changes" className="flex gap-4">
          <NavLink ticker={ticker} change={prev} dir="prev" />
          <NavLink ticker={ticker} change={next} dir="next" />
        </nav>
      </PageContainer>
    </>
  );
}
