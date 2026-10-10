/** Company page building blocks (server components). Sections are separated by spacing and one rule. */
import type { Comparison, FilingMeta } from "@/types/comparison";

import { CopyId } from "@/components/CopyId";
import { HighlightCard, groupHighlights } from "@/components/HighlightCard";
import { LibraryStatusLine } from "@/components/LibraryStatus";
import { FilingLink, Legend, SectionTitle } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { displayName } from "@/lib/names";
import type { LibraryStatus } from "@/lib/types";
import { AUDIT_TRAIL, meaningfulCount } from "@/lib/vocabulary";

export function OverviewHeader({ comparison }: { comparison: Comparison }) {
  const { company, old_filing, new_filing } = comparison;
  const name = displayName(company.name);
  const counts = comparison.summary.by_change_type ?? {};
  const { meaningful, unchanged, total: summed } = meaningfulCount(counts);
  const total = comparison.summary.total_changes || summed;
  return (
    <header>
      <p className="text-sm text-ink-secondary">
        {company.ticker}, annual reports FY{old_filing.fiscal_year} and FY{new_filing.fiscal_year}
      </p>
      <h1 className="mt-1 text-xl font-medium leading-tight tracking-tight text-ink">{name}</h1>
      <p className="mt-4 max-w-prose-72 text-lg font-medium leading-snug text-ink">
        {meaningful} of {total} risk {total === 1 ? "factor" : "factors"} changed meaningfully this year.
        {unchanged > 0 ? (
          <span className="font-normal text-ink-secondary">
            {" "}
            {unchanged} {unchanged === 1 ? "is" : "are"} essentially unchanged.
          </span>
        ) : null}
      </p>
      <p className="mt-2 max-w-prose-72 text-sm text-ink-secondary">
        Filed {formatDate(old_filing.filing_date)} and {formatDate(new_filing.filing_date)}. Every quote is verbatim from the filings.
        {comparison.summary.interpretation_status !== "ok" ? " AI summaries were not generated for this comparison." : ""}
      </p>
      <Legend className="mt-4" />
    </header>
  );
}

export function HighlightCards({ comparison }: { comparison: Comparison }) {
  const groups = groupHighlights(comparison);
  return (
    <section aria-labelledby="highlights-heading" className="space-y-4">
      <SectionTitle id="highlights-heading">Biggest changes</SectionTitle>
      {groups.length === 0 ? (
        <p className="text-base text-ink-secondary">No single sentence-level change stood out. Every change is listed below.</p>
      ) : (
        <ol className="space-y-4">
          {groups.map((g, i) => (
            <li key={g.change.id} data-highlight-card={i === 0 ? "first" : undefined}>
              <HighlightCard change={g.change} facts={g.facts} comparison={comparison} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function FilingFacts({ filing, role, isFixture, cik }: { filing: FilingMeta; role: string; isFixture: boolean; cik: string }) {
  return (
    <section aria-label={`${role} filing`} className="min-w-0">
      <h4 className="text-base font-medium text-ink">
        {role}: {filing.form}, FY{filing.fiscal_year}
      </h4>
      <dl className="mt-2 grid grid-cols-[160px_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-secondary">Form</dt>
        <dd className="text-ink">
          {filing.form}
          {filing.is_amendment ? " (amendment)" : ""}
        </dd>
        <dt className="text-ink-secondary">Accession number</dt>
        <dd className="break-all font-mono text-ink">{filing.accession_number}</dd>
        <dt className="text-ink-secondary">CIK</dt>
        <dd className="font-mono text-ink">{cik}</dd>
        <dt className="text-ink-secondary">Period of report</dt>
        <dd className="text-ink">{formatDate(filing.period_of_report)}</dd>
        <dt className="text-ink-secondary">Filing date</dt>
        <dd className="text-ink">{formatDate(filing.filing_date)}</dd>
        <dt className="text-ink-secondary">Primary document</dt>
        <dd className="break-all font-mono text-ink">{filing.primary_document}</dd>
        <dt className="text-ink-secondary">Item 1A size</dt>
        <dd className="text-ink">
          {filing.item_1a_word_count.toLocaleString("en-US")} words, {filing.block_count} risk blocks
        </dd>
      </dl>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        <FilingLink href={filing.edgar_url} isFixture={isFixture}>
          EDGAR document
        </FilingLink>
        <FilingLink href={filing.edgar_index_url} isFixture={isFixture}>
          EDGAR filing index
        </FilingLink>
      </div>
    </section>
  );
}

const INTERPRETATION_STATUS_COPY: Record<string, string> = {
  unavailable:
    "The AI stage did not run for this comparison (no language-model provider responded). Diffs, signals and change levels are deterministic and unaffected; AI points are absent.",
  skipped: "No change needed the AI stage, so it was not run. Diffs, signals and change levels are unaffected.",
  empty:
    "The language model ran, but the citation validator dropped every summary point it produced (uncited, invalid or disallowed wording). Diffs, signals and change levels are unaffected.",
};

export function AuditTrail({ comparison, source, libraryStatus = "unknown" }: { comparison: Comparison; source: string; libraryStatus?: LibraryStatus }) {
  const { company, old_filing, new_filing, model_ids, summary } = comparison;
  const isFixture = comparison.is_fixture === true;
  const changeModelIds = [...new Set(comparison.changes.map((c) => c.interpretation.model_id).filter((m): m is string => !!m))];
  return (
    <details className="group border-t border-line pt-4" id="audit-trail">
      <summary className="flex cursor-pointer list-none items-baseline gap-3">
        <span aria-hidden="true" className="text-ink-secondary transition group-open:rotate-90">
          ▸
        </span>
        <span className="text-lg font-medium text-ink">{AUDIT_TRAIL}</span>
        <span className="text-sm text-ink-secondary">Official name, filings, analysis id, versions and models behind this analysis</span>
      </summary>
      <div className="mt-5 space-y-6 text-sm">
        <p className="max-w-prose-72 text-base text-ink">Same filings and same software version always produce the same analysis id. Re-run it and compare.</p>
        <dl className="grid grid-cols-[160px_minmax(0,1fr)] gap-x-4 gap-y-1">
          <dt className="text-ink-secondary">Official SEC name</dt>
          <dd className="text-ink">{company.name}</dd>
          <dt className="text-ink-secondary">Ticker</dt>
          <dd className="font-mono text-ink">{company.ticker}</dd>
        </dl>
        <div className="grid gap-8 min-[900px]:grid-cols-2">
          <FilingFacts filing={old_filing} role="Last year" isFixture={isFixture} cik={company.cik} />
          <FilingFacts filing={new_filing} role="This year" isFixture={isFixture} cik={company.cik} />
        </div>
        <p className="text-ink-secondary">
          <span className="font-medium text-ink">Filing selection:</span> {comparison.filing_selection_note}
          {source === "api" ? " Served by the live API." : ""}
        </p>
        <LibraryStatusLine status={libraryStatus} size="sm" />
        <div className="grid gap-x-10 gap-y-2 min-[900px]:grid-cols-2">
          <dl className="grid grid-cols-[160px_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5">
            <dt className="text-ink-secondary">Analysis id</dt>
            <dd className="min-w-0">
              <CopyId value={comparison.analysis_id} />
            </dd>
            {comparison.code_fingerprint ? (
              <>
                <dt className="text-ink-secondary">Code fingerprint</dt>
                <dd className="min-w-0">
                  <CopyId value={comparison.code_fingerprint} label="code fingerprint" />
                </dd>
              </>
            ) : null}
            <dt className="text-ink-secondary">Pipeline version</dt>
            <dd className="font-mono text-ink">{comparison.pipeline_version}</dd>
            <dt className="text-ink-secondary">Rubric version</dt>
            <dd className="font-mono text-ink">{comparison.rubric_version}</dd>
            <dt className="text-ink-secondary">Schema version</dt>
            <dd className="font-mono text-ink">{comparison.schema_version}</dd>
            <dt className="text-ink-secondary">Blocks matched</dt>
            <dd className="text-ink">
              {summary.matched_pairs} pairs ({summary.old_block_count} old, {summary.new_block_count} new blocks)
            </dd>
          </dl>
          <dl className="grid grid-cols-[160px_minmax(0,1fr)] gap-x-4 gap-y-1.5">
            <dt className="text-ink-secondary">Embedding model</dt>
            <dd className="break-words font-mono text-ink">
              {model_ids.embedding_model} <span className="font-sans text-ink-secondary">({model_ids.embedding_backend})</span>
            </dd>
            <dt className="text-ink-secondary">Language model</dt>
            <dd className="break-words font-mono text-ink">
              {model_ids.llm_model ? (
                <>
                  {model_ids.llm_model}
                  {model_ids.llm_provider ? <span className="font-sans text-ink-secondary"> via {model_ids.llm_provider}</span> : null}
                </>
              ) : changeModelIds.length > 0 ? (
                <>
                  {changeModelIds.join(", ")}
                  <span className="block font-sans text-ink-secondary">Not recorded at the comparison level; taken from the per-change records.</span>
                </>
              ) : (
                <span className="font-sans text-ink-secondary">not used</span>
              )}
            </dd>
            <dt className="text-ink-secondary">NER model</dt>
            <dd className="break-words font-mono text-ink">{model_ids.ner_model}</dd>
            <dt className="text-ink-secondary">Sentence splitter</dt>
            <dd className="break-words font-mono text-ink">{model_ids.sentence_splitter}</dd>
            <dt className="text-ink-secondary">Categories</dt>
            <dd className="break-words font-mono text-ink">{model_ids.category_method}</dd>
            {model_ids.prompt_sha256 ? (
              <>
                <dt className="text-ink-secondary">Prompt sha256</dt>
                <dd className="min-w-0">
                  <CopyId value={model_ids.prompt_sha256} label="prompt sha256" />
                </dd>
              </>
            ) : null}
          </dl>
        </div>
        {model_ids.embedding_backend === "lexical-fallback" ? (
          <p className="border-l-2 border-actual-fg bg-actual-bg px-3 py-2 text-actual-fg">
            <span className="font-medium">Lexical fallback embedder.</span> Risk blocks were matched with a deterministic word-overlap embedder instead of the
            neural embedding model (it was unavailable when this comparison was produced). Matching of heavily reworded risks may be less accurate.
          </p>
        ) : null}
        {summary.interpretation_status !== "ok" ? (
          <p className="border-l-2 border-actual-fg bg-actual-bg px-3 py-2 text-actual-fg">
            <span className="font-medium">AI stage: {summary.interpretation_status}.</span>{" "}
            {INTERPRETATION_STATUS_COPY[summary.interpretation_status] ?? "The AI stage did not complete for this comparison."}
          </p>
        ) : null}
        {comparison.notes && comparison.notes.length > 0 ? (
          <div>
            <h4 className="font-medium text-ink">Notes</h4>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-secondary">
              {comparison.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}
