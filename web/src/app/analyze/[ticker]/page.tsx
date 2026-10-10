import type { Metadata } from "next";
import Link from "next/link";

import { AnalyzeRunner } from "@/components/AnalyzeRunner";
import { TickerSearch } from "@/components/TickerSearch";
import { PageContainer } from "@/components/ui";
import { normalizeTicker, TICKER_HELP } from "@/lib/ticker";

export const dynamic = "force-dynamic";

export async function generateMetadata(props: PageProps<"/analyze/[ticker]">): Promise<Metadata> {
  const { ticker } = await props.params;
  const t = normalizeTicker(ticker);
  return { title: t ? `Analyzing ${t}` : "Invalid ticker" };
}

export default async function AnalyzePage(props: PageProps<"/analyze/[ticker]">) {
  const { ticker: raw } = await props.params;
  const ticker = normalizeTicker(raw);

  if (!ticker) {
    return (
      <PageContainer className="max-w-[760px] py-20">
        <p className="font-mono text-sm font-semibold text-del-fg">
          <span aria-hidden="true">✕ </span>Invalid ticker
        </p>
        <h1 className="mt-2 text-3xl font-bold text-ink">That is not a valid ticker symbol.</h1>
        <p className="mt-3 text-ink-muted">{TICKER_HELP}</p>
        <div className="mt-8 max-w-[560px]">
          <TickerSearch size="large" />
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="space-y-6 py-8">
      <nav aria-label="Breadcrumb" className="text-sm text-ink-faint">
        <Link href="/" className="underline hover:text-ink">
          Home
        </Link>{" "}
        <span aria-hidden="true">/</span> <span className="text-ink">Live analysis</span>
      </nav>
      <div>
        <p className="font-mono text-sm font-bold tracking-wide text-accent">{ticker}</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-ink">Live analysis</h1>
        <p className="mt-1 max-w-[70ch] text-ink-muted">
          Comparing Item 1A (Risk Factors) of {ticker}&apos;s two most recent 10-K filings. You will be taken to the
          comparison when it is published.
        </p>
      </div>
      <AnalyzeRunner ticker={ticker} />
    </PageContainer>
  );
}
