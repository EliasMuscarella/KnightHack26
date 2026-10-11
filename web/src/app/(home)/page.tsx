import Link from "next/link";

import { CompanyGrid } from "@/components/CompanyGrid";
import { HeroSpecimen } from "@/components/HeroSpecimen";
import { TickerTape } from "@/components/TickerTape";
import { TickerSearch } from "@/components/TickerSearch";
import { EmptyState, FixtureBanner, PageContainer, SectionTitle } from "@/components/ui";
import { getTickerTapeFromApi } from "@/lib/api";
import { getSpecimens, listCompanies } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  // The tape waits at most 1.5s here (in parallel with the library listing); it refreshes client-side.
  const [companies, specimens, tape] = await Promise.all([listCompanies(), getSpecimens(), getTickerTapeFromApi(1500)]);
  const hasFixture = companies.some((c) => c.is_fixture);
  const reports = companies.filter((c) => !c.is_fixture);

  return (
    <>
      <TickerTape initial={tape} />
      {hasFixture ? <FixtureBanner /> : null}
      <section className="border-b border-line bg-surface">
        <PageContainer className="py-12">
          <div className="grid items-start gap-12 min-[1100px]:grid-cols-[minmax(0,1fr)_minmax(0,520px)]">
            <div>
              <h1 className="max-w-[22ch] text-2xl font-title leading-tight tracking-tight text-ink">
                See exactly what companies changed in their risk disclosures.
              </h1>
              <div className="mt-8 max-w-[640px]">
                <TickerSearch size="large" knownTickers={companies.map((c) => c.ticker)} />
                <p className="mt-2 text-sm text-ink-secondary">
                  Reports in the library open instantly. Any other ticker starts a live comparison of its two latest 10-K filings (a few minutes).
                </p>
              </div>
            </div>
            <HeroSpecimen slides={specimens} />
          </div>
        </PageContainer>
      </section>

      <PageContainer className="py-10">
        <SectionTitle
          id="library-heading"
          aside={
            reports.length > 0 ? (
              <>
                {reports.length} {reports.length === 1 ? "report" : "reports"}.{" "}
                <Link href="/trends" className="underline hover:text-ink">
                  Trends across the library
                </Link>
              </>
            ) : null
          }
        >
          Report library
        </SectionTitle>
        {companies.length === 0 ? (
          <EmptyState title="No published comparisons yet.">
            <p>Enter a ticker above to compare a company live</p>
          </EmptyState>
        ) : (
          <div className="mt-4">
            <CompanyGrid companies={companies} />
          </div>
        )}
      </PageContainer>
    </>
  );
}
