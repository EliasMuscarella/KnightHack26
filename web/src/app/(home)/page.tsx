import Link from "next/link";

import { CompanyGrid } from "@/components/CompanyGrid";
import { TickerSearch } from "@/components/TickerSearch";
import { EmptyState, FixtureBanner, PageContainer } from "@/components/ui";
import { listCompanies } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const companies = await listCompanies();
  const hasFixture = companies.some((c) => c.is_fixture);

  return (
    <>
      {hasFixture ? <FixtureBanner /> : null}
      <section className="border-b border-line bg-surface">
        <PageContainer className="grid grid-cols-[minmax(0,1fr)_420px] items-center gap-16 py-14">
          <div>
            <p className="font-mono text-sm font-semibold uppercase tracking-widest text-ink-faint">
              10-K · Item 1A · Risk Factors
            </p>
            <h1 className="mt-3 text-4xl font-bold leading-tight tracking-tight text-ink">
              GitHub Diff for SEC filings.
            </h1>
            <p className="mt-4 max-w-[62ch] text-lg leading-relaxed text-ink-muted">
              RiskDiff compares the Risk Factors section of a company&apos;s two most recent 10-K filings and shows
              exactly what management added, removed, expanded, or reworded, with every claim cited to the original
              filing text.
            </p>
            <div className="mt-8 max-w-[640px]">
              <TickerSearch size="large" knownTickers={companies.map((c) => c.ticker)} />
              <p className="mt-2 text-sm text-ink-faint">
                Published comparisons open instantly. Other tickers start a live analysis.
              </p>
            </div>
          </div>
          <ol className="space-y-3 rounded-lg border border-line bg-paper p-6 text-sm">
            <li className="flex gap-3">
              <span className="font-mono font-bold text-ink-faint">1</span>
              <span>
                <strong>Deterministic diff.</strong> Code, not a language model, decides what changed, sentence by
                sentence and word by word.
              </span>
            </li>
            <li className="flex gap-3">
              <span className="font-mono font-bold text-ink-faint">2</span>
              <span>
                <strong>Cited, always.</strong> Every score point and every AI sentence links to the filing sentences
                behind it.
              </span>
            </li>
            <li className="flex gap-3">
              <span className="font-mono font-bold text-ink-faint">3</span>
              <span>
                <strong>Reproducible.</strong> Same filings and same versions give the same output and the same
                analysis id.{" "}
                <Link href="/methodology" className="text-accent underline">
                  Methodology
                </Link>
              </span>
            </li>
          </ol>
        </PageContainer>
      </section>

      <PageContainer className="py-10">
        <div className="mb-5 flex items-baseline justify-between">
          <h2 className="text-xl font-bold text-ink">Published comparisons</h2>
          {companies.length > 0 ? (
            <p className="text-sm text-ink-faint">
              {companies.length} {companies.length === 1 ? "company" : "companies"}
            </p>
          ) : null}
        </div>
        {companies.length === 0 ? (
          <EmptyState title="No published comparisons yet.">
            <p>
              Run <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-sm text-ink">uv run python -m pipeline.run NVDA</code>{" "}
              or analyze a ticker live with the search box above.
            </p>
          </EmptyState>
        ) : (
          <CompanyGrid companies={companies} />
        )}
      </PageContainer>
    </>
  );
}
