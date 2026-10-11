import type { Metadata } from "next";

import { BriefingDocument } from "@/components/briefing/BriefingDocument";
import { BriefingPrintMode } from "@/components/briefing/BriefingPrintMode";
import { FIXTURE_BRIEFING } from "@/lib/briefing/fixture";
import { loadBriefing } from "@/lib/briefing/load";
import { parseSelection } from "@/lib/briefing/selection";
import { fixtureEnabled } from "@/lib/data";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Disclosure Briefing", robots: { index: false, follow: false } };

type SearchParams = Record<string, string | string[] | undefined>;

/**
 * The bare briefing document, for printing and for the PDF endpoint (which waits for
 * `data-briefing-ready`). The FIXTURE model renders only in development with the fixture enabled.
 */
export default async function BriefingPrintPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const useFixture = fixtureEnabled() && params.fixture === "1";
  const model = useFixture ? FIXTURE_BRIEFING : await loadBriefing(parseSelection(params));
  if (!model) {
    return (
      <main data-briefing-ready="1" data-briefing-empty="1">
        <BriefingPrintMode />
        <div className="briefing-empty">
          <p className="text-lg font-medium text-ink">No briefing to show.</p>
          <p className="mt-2 text-base text-ink-secondary">
            None of the requested companies is in the report library. Choose companies with a published report and try again.
          </p>
        </div>
      </main>
    );
  }
  return (
    <main data-briefing-ready="1">
      <BriefingPrintMode />
      <BriefingDocument model={model} />
    </main>
  );
}
