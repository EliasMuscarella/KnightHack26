import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ChangeList, type ChangeRow } from "@/components/ChangeList";
import { ComparisonHeader } from "@/components/ComparisonHeader";
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
    title: c.title,
    change_type: c.change_type,
    categories: c.categories,
    section_group: c.section_group ?? null,
    score: c.score,
    added: c.stats.added,
    removed: c.stats.removed,
    modified: c.stats.modified,
  }));

  return (
    <>
      {comparison.is_fixture ? <FixtureBanner /> : null}
      <PageContainer className="space-y-10 py-8">
        <nav aria-label="Breadcrumb" className="text-sm text-ink-faint">
          <Link href="/" className="underline hover:text-ink">
            Home
          </Link>{" "}
          <span aria-hidden="true">/</span> <span className="font-mono text-ink">{comparison.company.ticker}</span>
          {source === "api" ? <span className="ml-3 rounded bg-sunken px-1.5 py-px text-xs">served by the live API</span> : null}
        </nav>
        <ComparisonHeader comparison={comparison} />
        {comparison.changes.length === 0 ? (
          <InfoBox title="No risk factor changes">
            The two filings&apos; Item 1A sections did not produce any matched or unmatched risk blocks.
          </InfoBox>
        ) : (
          <ChangeList
            ticker={comparison.company.ticker}
            rows={rows}
            countsByType={comparison.summary.by_change_type ?? {}}
          />
        )}
      </PageContainer>
    </>
  );
}
