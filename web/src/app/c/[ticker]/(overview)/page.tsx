import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ChangeList, type ChangeRow } from "@/components/ChangeList";
import { AuditTrail, HighlightCards, OverviewHeader } from "@/components/Overview";
import { FixtureBanner, InfoBox, PageContainer } from "@/components/ui";
import { getComparison, getLibraryStatus } from "@/lib/data";
import { normalizeTicker } from "@/lib/ticker";

export const dynamic = "force-dynamic";

export async function generateMetadata(props: PageProps<"/c/[ticker]">): Promise<Metadata> {
  const { ticker: raw } = await props.params;
  const ticker = normalizeTicker(raw);
  return { title: ticker ? `${ticker} risk factor changes` : "Comparison" };
}

export default async function ComparisonPage(props: PageProps<"/c/[ticker]">) {
  const { ticker: raw } = await props.params;
  const search = await props.searchParams;
  const rawTopic = Array.isArray(search?.topic) ? search?.topic[0] : search?.topic;
  const initialTopic = typeof rawTopic === "string" && /^[a-z_]{1,40}$/.test(rawTopic) ? rawTopic : "";
  const ticker = normalizeTicker(raw);
  if (!ticker) notFound();
  const [result, libraryStatus] = await Promise.all([getComparison(ticker), getLibraryStatus()]);
  if (!result) notFound();
  const { comparison, source } = result;

  const rows: ChangeRow[] = comparison.changes.map((c) => ({
    id: c.id,
    rank: c.rank,
    short_title: c.short_title,
    title: c.title,
    change_type: c.change_type,
    categories: c.categories,
    score: c.score,
    added: c.stats.added,
    removed: c.stats.removed,
    modified: c.stats.modified,
  }));

  return (
    <>
      {comparison.is_fixture ? <FixtureBanner /> : null}
      <PageContainer className="space-y-10 py-10">
        <OverviewHeader comparison={comparison} />
        {comparison.changes.length === 0 ? (
          <InfoBox title="No risk factor changes">
            The Risk Factors sections of the two filings did not produce any matched or unmatched risk factors.
          </InfoBox>
        ) : (
          <>
            <HighlightCards comparison={comparison} />
            <ChangeList ticker={comparison.company.ticker} rows={rows} initialTopic={initialTopic} companyName={comparison.company.name} />
          </>
        )}
        <AuditTrail comparison={comparison} source={source} libraryStatus={libraryStatus} />
      </PageContainer>
    </>
  );
}
