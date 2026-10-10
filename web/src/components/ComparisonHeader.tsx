import type { Comparison, FilingMeta, InterpretationStatus } from "@/types/comparison";

import { CopyId } from "@/components/CopyId";
import { FilingLink, InfoBox } from "@/components/ui";
import { formatDate } from "@/lib/format";

function FilingCard({ filing, role, isFixture }: { filing: FilingMeta; role: "Older" | "Newer"; isFixture: boolean }) {
  return (
    <section
      aria-label={`${role} filing`}
      className="flex-1 rounded-lg border border-line bg-surface p-5"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">{role} filing</h3>
        <span className="font-mono text-xs text-ink-faint">{filing.primary_document}</span>
      </div>
      <p className="mt-1 text-2xl font-bold text-ink">
        {filing.form} <span className="text-ink-muted">· FY{filing.fiscal_year}</span>
      </p>
      <dl className="mt-3 grid grid-cols-[150px_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-ink-faint">Period of report</dt>
        <dd className="text-ink">{formatDate(filing.period_of_report)}</dd>
        <dt className="text-ink-faint">Filing date</dt>
        <dd className="text-ink">{formatDate(filing.filing_date)}</dd>
        <dt className="text-ink-faint">Accession number</dt>
        <dd className="font-mono text-ink">{filing.accession_number}</dd>
        <dt className="text-ink-faint">Item 1A size</dt>
        <dd className="text-ink">
          {filing.item_1a_word_count.toLocaleString("en-US")} words · {filing.block_count} risk blocks
        </dd>
      </dl>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm font-medium">
        <FilingLink href={filing.edgar_url} isFixture={isFixture}>
          Filing document on EDGAR
        </FilingLink>
        <FilingLink href={filing.edgar_index_url} isFixture={isFixture}>
          Filing index
        </FilingLink>
      </div>
    </section>
  );
}

const INTERPRETATION_STATUS_COPY: Partial<Record<InterpretationStatus, { title: string; body: string }>> = {
  unavailable: {
    title: "AI interpretation unavailable",
    body: "The AI rubric and interpretation stage did not run for this comparison (the reason is in the notes, when recorded). Diffs, signals and scores are deterministic and unaffected; AI rubric points are absent.",
  },
  skipped: {
    title: "AI interpretation skipped",
    body: "No change in this comparison needed the AI rubric and interpretation stage, so it was not run. Diffs, signals and scores are deterministic and unaffected.",
  },
  empty: {
    title: "No validated AI claims",
    body: "The language model ran, but the citation validator dropped every interpretation claim it produced (uncited, invalid or disallowed wording). Rubric answers may still be shown on individual changes. Diffs, signals and scores are deterministic and unaffected.",
  },
};

export function ComparisonHeader({ comparison }: { comparison: Comparison }) {
  const { company, old_filing, new_filing, model_ids, summary } = comparison;
  const isFixture = comparison.is_fixture === true;
  // Provenance fallback: the top-level llm_model can be null while individual changes
  // still record the model that produced their interpretation.
  const changeModelIds = [
    ...new Set(comparison.changes.map((c) => c.interpretation.model_id).filter((m): m is string => !!m)),
  ];
  const interpretationStatus = summary.interpretation_status;
  return (
    <div className="space-y-6">
      <div>
        <p className="font-mono text-sm font-bold tracking-wide text-accent">{company.ticker}</p>
        <h1 className="mt-1 text-3xl font-bold leading-tight tracking-tight text-ink">{company.name}</h1>
        <p className="mt-1 text-sm text-ink-muted">
          CIK <span className="font-mono">{company.cik}</span> · Item 1A (Risk Factors), FY{old_filing.fiscal_year}{" "}
          <span aria-hidden="true">→</span>
          <span className="sr-only">compared with</span> FY{new_filing.fiscal_year}
        </p>
      </div>

      <div className="flex items-stretch gap-4">
        <FilingCard filing={old_filing} role="Older" isFixture={isFixture} />
        <div aria-hidden="true" className="flex items-center font-mono text-2xl text-ink-faint">
          →
        </div>
        <FilingCard filing={new_filing} role="Newer" isFixture={isFixture} />
      </div>

      <details open className="group rounded-lg border border-line bg-surface">
        <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-3 text-sm">
          <span aria-hidden="true" className="font-mono text-ink-faint transition group-open:rotate-90">
            ▸
          </span>
          <span className="font-semibold text-ink">Provenance</span>
          <span className="text-ink-faint">analysis id, versions and models</span>
          <span className="ml-auto text-xs text-ink-faint">{comparison.filing_selection_note}</span>
        </summary>
        <div className="grid grid-cols-2 gap-x-10 gap-y-2 border-t border-line px-5 py-4 text-sm">
          <dl className="grid grid-cols-[150px_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5">
            <dt className="text-ink-faint">Analysis id</dt>
            <dd className="min-w-0">
              <CopyId value={comparison.analysis_id} />
            </dd>
            {comparison.code_fingerprint ? (
              <>
                <dt className="text-ink-faint">Code fingerprint</dt>
                <dd className="min-w-0">
                  <CopyId value={comparison.code_fingerprint} label="code fingerprint" />
                </dd>
              </>
            ) : null}
            <dt className="text-ink-faint">Pipeline version</dt>
            <dd className="font-mono text-ink">{comparison.pipeline_version}</dd>
            <dt className="text-ink-faint">Rubric version</dt>
            <dd className="font-mono text-ink">{comparison.rubric_version}</dd>
            <dt className="text-ink-faint">Schema version</dt>
            <dd className="font-mono text-ink">{comparison.schema_version}</dd>
            <dt className="text-ink-faint">Blocks matched</dt>
            <dd className="text-ink">
              {summary.matched_pairs} pairs ({summary.old_block_count} old, {summary.new_block_count} new blocks)
            </dd>
          </dl>
          <dl className="grid grid-cols-[150px_minmax(0,1fr)] gap-x-4 gap-y-1.5">
            <dt className="text-ink-faint">Embedding model</dt>
            <dd className="break-words font-mono text-ink">
              {model_ids.embedding_model}{" "}
              <span className="font-sans text-ink-faint">({model_ids.embedding_backend})</span>
            </dd>
            <dt className="text-ink-faint">Language model</dt>
            <dd className="break-words font-mono text-ink">
              {model_ids.llm_model ? (
                <>
                  {model_ids.llm_model}
                  {model_ids.llm_provider ? <span className="font-sans text-ink-faint"> via {model_ids.llm_provider}</span> : null}
                </>
              ) : changeModelIds.length > 0 ? (
                <>
                  {changeModelIds.join(", ")}
                  <span className="block font-sans text-xs text-ink-faint">
                    Not recorded at the comparison level; taken from the per-change interpretation records.
                  </span>
                </>
              ) : (
                <span className="font-sans text-ink-faint">not used</span>
              )}
            </dd>
            <dt className="text-ink-faint">NER model</dt>
            <dd className="break-words font-mono text-ink">{model_ids.ner_model}</dd>
            <dt className="text-ink-faint">Sentence splitter</dt>
            <dd className="break-words font-mono text-ink">{model_ids.sentence_splitter}</dd>
            <dt className="text-ink-faint">Categories</dt>
            <dd className="break-words font-mono text-ink">{model_ids.category_method}</dd>
            {model_ids.prompt_sha256 ? (
              <>
                <dt className="text-ink-faint">Prompt sha256</dt>
                <dd className="min-w-0">
                  <CopyId value={model_ids.prompt_sha256} label="prompt sha256" />
                </dd>
              </>
            ) : null}
          </dl>
        </div>
      </details>

      {model_ids.embedding_backend === "lexical-fallback" || interpretationStatus !== "ok" ? (
        <div className="grid grid-cols-2 gap-4">
          {model_ids.embedding_backend === "lexical-fallback" ? (
            <InfoBox title="Lexical fallback embedder" tone="warn">
              Risk blocks were matched with a deterministic word-overlap embedder instead of the neural embedding
              model (it was unavailable when this comparison was produced). Matching of heavily reworded risks may
              be less accurate.
            </InfoBox>
          ) : null}
          {interpretationStatus !== "ok" ? (
            <InfoBox title={INTERPRETATION_STATUS_COPY[interpretationStatus]?.title ?? "AI interpretation incomplete"} tone="warn">
              {INTERPRETATION_STATUS_COPY[interpretationStatus]?.body ??
                "The AI rubric and interpretation stage did not complete for this comparison. Diffs, signals and scores are deterministic and unaffected."}
            </InfoBox>
          ) : null}
        </div>
      ) : null}

      {comparison.notes && comparison.notes.length > 0 ? (
        <InfoBox title="Notes">
          <ul className="list-disc space-y-0.5 pl-5">
            {comparison.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </InfoBox>
      ) : null}
    </div>
  );
}
