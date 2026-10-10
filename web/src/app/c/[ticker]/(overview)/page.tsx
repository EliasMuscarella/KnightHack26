import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ChangeList, type ChangeRow } from "@/components/ChangeList";
import { AuditTrail, HighlightCards, OverviewHeader, SummaryLine } from "@/components/Overview";
import { FixtureBanner, InfoBox, PageContainer } from "@/components/ui";
import { getComparison } from "@/lib/data";
import { normalizeTicker } from "@/lib/ticker";

export const dynamic = "force-dynamic";

export async function generateMetadata(props: PageProps<"/c/[ticker]">): Promise<Metadata> {
  const { ticker: raw } = await props.params;
  const ticker = normalizeTicker(raw);
  return { title: ticker ? `${ticker} risk factor changes` : "Comparison" };
}

export default async function ComparisonPage(props: PageProps<"/c/[ticker]">) {
  const { ticker: raw } = await props.params;
  const ticker = normalizeTicker(raw);
  if (!ticker) notFound();
  const result = await getComparison(ticker);
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
      <PageContainer className="space-y-8 py-7">
        <div className="space-y-4">
          <OverviewHeader comparison={comparison} />
          <SummaryLine comparison={comparison} />
        </div>
        {comparison.changes.length === 0 ? (
          <InfoBox title="No risk factor changes">
            The Risk Factors sections of the two filings did not produce any matched or unmatched risk factors.
          </InfoBox>
        ) : (
          <>
            <HighlightCards comparison={comparison} />
            <ChangeList ticker={comparison.company.ticker} rows={rows} />
          </>
        )}
        <AuditTrail comparison={comparison} source={source} />
      </PageContainer>
    </>
  );
}
