import type { Metadata } from "next";
import Link from "next/link";

import { BriefingActions } from "@/components/BriefingActions";
import { BriefingPicker, type BriefingPickerCompany } from "@/components/BriefingPicker";
import { BriefingDocument } from "@/components/briefing/BriefingDocument";
import { EmptyState, InfoBox, PageContainer } from "@/components/ui";
import { loadBriefing } from "@/lib/briefing/load";
import { briefingFilename } from "@/lib/briefing/pdf";
import { parseSelection, selectionQuery, type BriefingSelection } from "@/lib/briefing/selection";
import { MAX_BRIEFING_COMPANIES } from "@/lib/briefing/types";
import { listCompanies } from "@/lib/data";
import { displayName } from "@/lib/names";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Disclosure Briefing" };

const INTRO = `A printable briefing on what changed in the Risk Factors sections of the latest 10-K filings, for up to ${MAX_BRIEFING_COMPANIES} companies you pick. Every quote is verbatim and every number comes from the filings.`;

/** "A, B and C". */
function listText(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** Quiet notes about the request: invalid entries, the cap, companies not in the library. Text only. */
function SelectionNotes({ sel, missing }: { sel: BriefingSelection; missing: string[] }) {
  const notes: string[] = [];
  if (sel.rejected.length) notes.push(`Not valid tickers, ignored: ${listText(sel.rejected.map((r) => `"${r}"`))}.`);
  if (sel.truncated) notes.push(`A briefing covers at most ${MAX_BRIEFING_COMPANIES} companies; the rest were left out.`);
  if (missing.length) notes.push(`Not in the library yet, left out: ${listText(missing)}.`);
  if (notes.length === 0) return null;
  return (
    <InfoBox>
      {notes.map((n) => (
        <p key={n}>{n}</p>
      ))}
    </InfoBox>
  );
}

async function pickerCompanies(): Promise<BriefingPickerCompany[]> {
  const listing = await listCompanies();
  return listing
    .map((c) => ({
      ticker: c.ticker,
      name: displayName(c.name),
      oldFiscalYear: c.old_fiscal_year,
      newFiscalYear: c.new_fiscal_year,
      isFixture: c.is_fixture === true,
    }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.ticker.localeCompare(b.ticker));
}

function PickerHeader() {
  return (
    <header className="space-y-3">
      <h1 className="text-xl font-medium text-ink">Disclosure Briefing</h1>
      <p className="max-w-prose-72 text-base text-ink-secondary">{INTRO}</p>
    </header>
  );
}

export default async function BriefingPage(props: PageProps<"/briefing">) {
  const sel = parseSelection(await props.searchParams);

  if (sel.tickers.length === 0) {
    return (
      <PageContainer className="space-y-8 py-10">
        <PickerHeader />
        <SelectionNotes sel={sel} missing={[]} />
        <BriefingPicker companies={await pickerCompanies()} />
      </PageContainer>
    );
  }

  const [model, companies] = await Promise.all([loadBriefing(sel), pickerCompanies()]);

  if (!model) {
    return (
      <PageContainer className="space-y-8 py-10">
        <PickerHeader />
        <EmptyState title="None of these companies are in the library yet">
          Pick from the companies below, or analyze a new company from the home page first.
        </EmptyState>
        <SelectionNotes sel={sel} missing={[]} />
        <BriefingPicker companies={companies} />
      </PageContainer>
    );
  }

  const included = model.companies.map((c) => c.ticker);
  const query = selectionQuery({ tickers: included, title: sel.title, preparedFor: sel.preparedFor });
  const count = included.length;

  return (
    <>
      <div className="briefing-preview-bar sticky top-14 z-30 border-b border-line bg-surface print:hidden">
        <PageContainer className="flex flex-wrap items-start justify-between gap-x-8 gap-y-2 pt-3 pb-1.5">
          <div className="pt-2">
            <p className="text-base text-ink">
              <span className="font-medium">
                {count} {count === 1 ? "company" : "companies"}:
              </span>{" "}
              {included.join(", ")}
            </p>
            <Link href="/briefing" className="text-sm text-accent underline underline-offset-2">
              Edit selection
            </Link>
          </div>
          <BriefingActions
            pdfHref={`/api/briefing.pdf?${query}`}
            printHref={`/briefing/print?${query}`}
            fallbackFilename={briefingFilename(included)}
            tickers={included}
            title={sel.title}
            preparedFor={sel.preparedFor}
          />
        </PageContainer>
      </div>
      <PageContainer className="space-y-6 py-8">
        <div className="print:hidden">
          <SelectionNotes sel={sel} missing={model.missingTickers} />
        </div>
        <BriefingDocument model={model} />
      </PageContainer>
    </>
  );
}
