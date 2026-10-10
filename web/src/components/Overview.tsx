/** Company overview building blocks (server components). */
import Link from "next/link";

import type { Change, Comparison, FilingMeta, Highlight } from "@/types/comparison";

import { CopyId } from "@/components/CopyId";
import { Quote } from "@/components/Quote";
import { FilingLink, HighlightKindBadge } from "@/components/ui";
import { LibraryStatusLine } from "@/components/LibraryStatus";
import { formatDate, textFragmentUrl } from "@/lib/format";
import type { LibraryStatus } from "@/lib/types";
import { AUDIT_TRAIL, displayTitle, highlightKindVocab, isFigureChanged, meaningfulCount } from "@/lib/vocabulary";

export function OverviewHeader({ comparison }: { comparison: Comparison }) {
  const { company, old_filing, new_filing } = comparison;
  return (
    <header>
      <p className="font-mono text-sm font-bold tracking-wide text-accent">{company.ticker}</p>
      <h1 className="mt-0.5 text-3xl font-bold leading-tight tracking-tight text-ink">{company.name}</h1>
      <p className="mt-1.5 text-base text-ink-muted">
        <span className="font-semibold text-ink">
          Annual report risk factors: FY{old_filing.fiscal_year} <span aria-hidden="true">→</span>
          <span className="sr-only">compared with</span> FY{new_filing.fiscal_year}
        </span>
        <span aria-hidden="true"> · </span>
        <span className="sr-only">. </span>
        filed {formatDate(old_filing.filing_date)} and {formatDate(new_filing.filing_date)}
      </p>
    </header>
  );
}

export function SummaryLine({ comparison }: { comparison: Comparison }) {
  const counts = comparison.summary.by_change_type ?? {};
  const { meaningful, unchanged, total: summed } = meaningfulCount(counts);
  const total = comparison.summary.total_changes || summed;
  return (
    <div>
      <p className="text-xl font-semibold leading-snug text-ink">
        {meaningful} of {total} risk {total === 1 ? "factor" : "factors"} changed meaningfully.{" "}
        <span className="font-normal text-ink-muted">
          {unchanged} {unchanged === 1 ? "was" : "were"} essentially unchanged from last year.
        </span>
      </p>
      <p className="mt-1 text-sm text-ink-faint">Every quote below is verbatim from the company&apos;s SEC filings.</p>
      {comparison.summary.interpretation_status !== "ok" ? (
        <p className="mt-1 text-sm text-ink-faint">AI summaries were not generated for this comparison.</p>
      ) : null}
    </div>
  );
}

function QuoteSide({
  label,
  fy,
  text,
  absent,
}: {
  label: string;
  fy: number;
  text: string | null;
  absent: string;
}) {
  return (
    <div className="min-w-0">
      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-ink-faint">
        {label} <span className="font-medium normal-case tracking-normal">· FY{fy}</span>
      </p>
      {text !== null ? (
        <Quote text={text} />
      ) : (
        <p className="rounded border border-dashed border-line-strong px-3 py-2 text-sm italic text-ink-muted">{absent}</p>
      )}
    </div>
  );
}

/** Kind-aware caption for an empty side: a new name or figure does not make the whole risk new. */
function absentCaptions(h: Highlight): { absentOld: string; absentNew: string } {
  const absentOld =
    h.kind === "new_risk"
      ? "Not in last year's filing"
      : h.kind === "new_named_party"
        ? "This name did not appear in last year's version"
        : h.kind === "new_figure"
          ? "This figure did not appear in last year's version"
          : "No matching sentence last year";
  const absentNew = h.kind === "removed_risk" ? "Removed this year" : "No matching sentence this year";
  return { absentOld, absentNew };
}

/** One highlight of a risk factor: its kind badge + helper, then the Last year / This year quotes. */
function HighlightFact({ h, comparison }: { h: Highlight; comparison: Comparison }) {
  const idx = comparison.sentence_index;
  const oldText = h.old_sentence_id ? (idx[h.old_sentence_id]?.text ?? null) : null;
  const newText = h.new_sentence_id ? (idx[h.new_sentence_id]?.text ?? null) : null;
  const figureChanged = isFigureChanged(h);
  const vocab = highlightKindVocab(h.kind, figureChanged);
  const { absentOld, absentNew } = absentCaptions(h);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <HighlightKindBadge kind={h.kind} figureChanged={figureChanged} />
        {vocab.helper ? <span className="text-sm text-ink-faint">{vocab.helper}</span> : null}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-6">
        <QuoteSide label="Last year" fy={comparison.old_filing.fiscal_year} text={oldText} absent={absentOld} />
        <QuoteSide label="This year" fy={comparison.new_filing.fiscal_year} text={newText} absent={absentNew} />
      </div>
    </div>
  );
}

/** One card per risk factor: the title once, one fact block per highlight, the links once. */
function HighlightCard({
  change,
  facts,
  comparison,
  first,
}: {
  change: Change;
  facts: Highlight[];
  comparison: Comparison;
  first: boolean;
}) {
  const idx = comparison.sentence_index;
  const ticker = comparison.company.ticker;
  // "View in SEC filing" opens this year's filing at the first fact with a this-year sentence;
  // a dropped risk (no this-year sentence anywhere) falls back to last year's filing.
  const textOf = (id: string | null | undefined) => (id ? (idx[id]?.text ?? null) : null);
  const newLink = facts.map((h) => textOf(h.new_sentence_id)).find((t): t is string => t !== null) ?? null;
  const oldLink = facts.map((h) => textOf(h.old_sentence_id)).find((t): t is string => t !== null) ?? null;
  const linkText = newLink ?? oldLink;
  const filing = newLink !== null ? comparison.new_filing : comparison.old_filing;
  return (
    <article
      data-highlight-card={first ? "first" : undefined}
      className="rounded-lg border border-line bg-surface p-5 shadow-sm"
    >
      <h3 className="text-lg font-bold leading-snug text-ink">{displayTitle(change.short_title, change.title)}</h3>
      <div className="mt-3 divide-y divide-line">
        {facts.map((h, i) => (
          <div key={i} className="py-4 first:pt-0 last:pb-0">
            <HighlightFact h={h} comparison={comparison} />
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-line pt-3 text-sm font-medium">
        {linkText !== null ? (
          <FilingLink href={textFragmentUrl(filing.edgar_url, linkText)} isFixture={comparison.is_fixture === true}>
            View in SEC filing
          </FilingLink>
        ) : null}
        <Link
          href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(change.id)}`}
          className="text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
        >
          See full change <span aria-hidden="true">→</span>
        </Link>
      </div>
    </article>
  );
}

export function HighlightCards({ comparison }: { comparison: Comparison }) {
  const byId = new Map(comparison.changes.map((c) => [c.id, c] as const));
  // Group highlights by risk factor, in order of first appearance.
  const groups: { change: Change; facts: Highlight[] }[] = [];
  const groupOf = new Map<string, { change: Change; facts: Highlight[] }>();
  for (const h of comparison.highlights ?? []) {
    const change = byId.get(h.change_id);
    if (!change) continue;
    let g = groupOf.get(h.change_id);
    if (!g) {
      g = { change, facts: [] };
      groupOf.set(h.change_id, g);
      groups.push(g);
    }
    g.facts.push(h);
  }
  return (
    <section aria-labelledby="highlights-heading" className="space-y-3">
      <h2 id="highlights-heading" className="text-xl font-bold text-ink">
        Biggest changes
      </h2>
      {groups.length === 0 ? (
        <p className="text-ink-muted">No single sentence-level change stood out. Every change is listed below.</p>
      ) : (
        <ol className="space-y-4">
          {groups.map((g, i) => (
            <li key={g.change.id}>
              <HighlightCard change={g.change} facts={g.facts} comparison={comparison} first={i === 0} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function FilingFacts({ filing, role, isFixture, cik }: { filing: FilingMeta; role: string; isFixture: boolean; cik: string }) {
  return (
    <section aria-label={`${role} filing`} className="min-w-0 rounded-md border border-line bg-paper p-4">
      <h4 className="text-sm font-bold text-ink">
        {role}: {filing.form} · FY{filing.fiscal_year}
      </h4>
      <dl className="mt-2 grid grid-cols-[150px_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-faint">Form</dt>
        <dd className="text-ink">
          {filing.form}
          {filing.is_amendment ? " (amendment)" : ""}
        </dd>
        <dt className="text-ink-faint">Accession number</dt>
        <dd className="break-all font-mono text-ink">{filing.accession_number}</dd>
        <dt className="text-ink-faint">CIK</dt>
        <dd className="font-mono text-ink">{cik}</dd>
        <dt className="text-ink-faint">Period of report</dt>
        <dd className="text-ink">{formatDate(filing.period_of_report)}</dd>
        <dt className="text-ink-faint">Filing date</dt>
        <dd className="text-ink">{formatDate(filing.filing_date)}</dd>
        <dt className="text-ink-faint">Primary document</dt>
        <dd className="break-all font-mono text-ink">{filing.primary_document}</dd>
        <dt className="text-ink-faint">Item 1A size</dt>
        <dd className="text-ink">
          {filing.item_1a_word_count.toLocaleString("en-US")} words · {filing.block_count} risk blocks
        </dd>
      </dl>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm font-medium">
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

export function AuditTrail({
  comparison,
  source,
  libraryStatus = "unknown",
}: {
  comparison: Comparison;
  source: string;
  libraryStatus?: LibraryStatus;
}) {
  const { company, old_filing, new_filing, model_ids, summary } = comparison;
  const isFixture = comparison.is_fixture === true;
  const changeModelIds = [
    ...new Set(comparison.changes.map((c) => c.interpretation.model_id).filter((m): m is string => !!m)),
  ];
  return (
    <details className="group rounded-lg border border-line bg-surface" id="audit-trail">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-4">
        <span aria-hidden="true" className="font-mono text-ink-faint transition group-open:rotate-90">
          ▸
        </span>
        <span className="text-lg font-bold text-ink">{AUDIT_TRAIL}</span>
        <span className="text-sm text-ink-faint">
          <span aria-hidden="true">· </span>filings, analysis id, versions and models behind this analysis
        </span>
      </summary>
      <div className="space-y-5 border-t border-line px-5 py-5 text-sm">
        <p className="text-base font-semibold text-ink">
          Same filings and same software version always produce the same analysis id. Re-run it and compare.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <FilingFacts filing={old_filing} role="Last year" isFixture={isFixture} cik={company.cik} />
          <FilingFacts filing={new_filing} role="This year" isFixture={isFixture} cik={company.cik} />
        </div>
        <p className="text-ink-muted">
          <span className="font-semibold text-ink">Filing selection:</span> {comparison.filing_selection_note}
          {source === "api" ? " · Served by the live API." : ""}
        </p>
        <LibraryStatusLine status={libraryStatus} size="sm" />
        <div className="grid grid-cols-2 gap-x-10 gap-y-2">
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
              {model_ids.embedding_model} <span className="font-sans text-ink-faint">({model_ids.embedding_backend})</span>
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
                    Not recorded at the comparison level; taken from the per-change records.
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
        {model_ids.embedding_backend === "lexical-fallback" ? (
          <p className="rounded border-l-4 border-mod-line bg-mod-bg px-3 py-2 text-mod-fg">
            <span className="font-semibold">Lexical fallback embedder.</span> Risk blocks were matched with a deterministic
            word-overlap embedder instead of the neural embedding model (it was unavailable when this comparison was
            produced). Matching of heavily reworded risks may be less accurate.
          </p>
        ) : null}
        {summary.interpretation_status !== "ok" ? (
          <p className="rounded border-l-4 border-mod-line bg-mod-bg px-3 py-2 text-mod-fg">
            <span className="font-semibold">AI stage: {summary.interpretation_status}.</span>{" "}
            {INTERPRETATION_STATUS_COPY[summary.interpretation_status] ?? "The AI stage did not complete for this comparison."}
          </p>
        ) : null}
        {comparison.notes && comparison.notes.length > 0 ? (
          <div>
            <h4 className="font-semibold text-ink">Notes</h4>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-muted">
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
