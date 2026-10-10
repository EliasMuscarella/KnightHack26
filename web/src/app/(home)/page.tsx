import Link from "next/link";

import { CompanyGrid } from "@/components/CompanyGrid";
import { TickerSearch } from "@/components/TickerSearch";
import { EmptyState, FixtureBanner, PageContainer } from "@/components/ui";
import { listCompanies } from "@/lib/data";

export const dynamic = "force-dynamic";

const BENEFITS = [
  {
    title: "Find what matters",
    body: "The few risk factors whose wording moved the most, out of 15,000+ words.",
  },
  {
    title: "Verify every word",
    body: "Every quote and AI statement links to the exact sentence in the SEC filing.",
  },
  {
    title: "Same answer every time",
    body: "The same filings always produce the same analysis, with a full audit trail.",
  },
];

export default async function HomePage() {
  const companies = await listCompanies();
  const hasFixture = companies.some((c) => c.is_fixture);

  return (
    <>
      {hasFixture ? <FixtureBanner /> : null}
      <section className="border-b border-line bg-surface">
        <PageContainer className="py-12">
          <h1 className="max-w-[24ch] text-4xl font-bold leading-tight tracking-tight text-ink">
            See what changed in a company&apos;s risk disclosures, in seconds.
          </h1>
          <p className="mt-4 max-w-[72ch] text-lg leading-relaxed text-ink-muted">
            RiskDiff compares a company&apos;s last two annual reports (10-K) and surfaces exactly what management added,
            removed, or changed in its risk factors, with every quote linked to the SEC filing.
          </p>
          <div className="mt-7 max-w-[640px]">
            <TickerSearch size="large" knownTickers={companies.map((c) => c.ticker)} />
            <p className="mt-2 text-sm text-ink-faint">
              Published companies open instantly. Other tickers start a live analysis (a few minutes).
            </p>
          </div>
          <ul className="mt-9 grid grid-cols-3 gap-5">
            {BENEFITS.map((b) => (
              <li key={b.title} className="rounded-lg border border-line bg-paper px-5 py-4">
                <p className="text-base font-bold text-ink">{b.title}</p>
                <p className="mt-1 text-base leading-snug text-ink-muted">{b.body}</p>
              </li>
            ))}
          </ul>
        </PageContainer>
      </section>

      <PageContainer className="py-10">
        <div className="mb-5 flex items-baseline justify-between">
          <h2 className="text-xl font-bold text-ink">Companies</h2>
          {companies.length > 0 ? (
            <p className="text-sm text-ink-faint">
              {companies.length} {companies.length === 1 ? "company" : "companies"} ·{" "}
              <Link href="/methodology" className="underline hover:text-ink">
                How it works
              </Link>
            </p>
          ) : null}
        </div>
        {companies.length === 0 ? (
          <EmptyState title="No published comparisons yet.">
            <p>
              Enter a ticker above to analyze a company live, or publish one with{" "}
              <code className="whitespace-nowrap rounded bg-sunken px-1.5 py-0.5 font-mono text-sm text-ink">uv run python -m pipeline.run NVDA</code>.
            </p>
          </EmptyState>
        ) : (
          <CompanyGrid companies={companies} />
        )}
      </PageContainer>
    </>
  );
}
