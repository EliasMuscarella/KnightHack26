"use client";

import { useState } from "react";

import type { Change, Interpretation, ModelIds, ScoreLine, SignalHit, Signals } from "@/types/comparison";

import { CitationChips, useCitations } from "@/components/citations";
import { ChangeLevel, SectionTitle } from "@/components/ui";
import { categoryLabel, formatRatio, formatShare } from "@/lib/format";
import {
  AI_SUMMARY,
  ANALYST_DETAILS,
  CHANGE_LEVEL,
  changeLevel,
  figureVariant,
  figureVocab,
  type FigureVariant,
  scoreLineHelper,
  scoreLineLabel,
  SIGNAL_VOCAB,
} from "@/lib/vocabulary";

// ---------------------------------------------------------------------------------------
// What changed (AI summary)
// ---------------------------------------------------------------------------------------

export function WhatChangedPanel({ interp, numberOf }: { interp: Interpretation; numberOf: (id: string) => number }) {
  const claims = interp.status === "ok" ? (interp.claims ?? []) : [];
  return (
    <section aria-labelledby="what-changed-heading" className="space-y-4">
      <SectionTitle id="what-changed-heading">What changed</SectionTitle>
      {claims.length === 0 ? (
        <p className="text-base text-ink-secondary">No AI summary for this change.</p>
      ) : (
        <div className="max-w-[90ch] rounded-lg bg-signal-bg p-6">
          <p className="flex items-center gap-2 text-sm font-medium text-ink">
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" className="text-ink-secondary">
              <path d="M3 2.5h7l3 3v8a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
              <path d="M10 2.5v3h3M5 8h6M5 10.5h6" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
            {AI_SUMMARY.label}
          </p>
          <ol className="mt-3 list-decimal space-y-2.5 pl-5 text-base leading-relaxed text-ink">
            {claims.map((c, i) => (
              <li key={i} className="pl-1">
                {c.text}
                <CitationChips ids={c.cited_sentence_ids} numberOf={numberOf} withSide />
              </li>
            ))}
          </ol>
          <p className="mt-4 text-sm text-ink-secondary">
            Every point cites the filing. A superscript number jumps to that sentence below.
          </p>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// How this was scored
// ---------------------------------------------------------------------------------------

function CitedSentenceList({ ids }: { ids: string[] }) {
  const { index, filings, jumpTo } = useCitations();
  if (ids.length === 0) return <p className="text-sm text-ink-secondary">No sentences cited.</p>;
  return (
    <ol className="space-y-2">
      {ids.map((id, i) => {
        const ref = index[id];
        const fy = ref ? (ref.side === "old" ? filings.old.fiscal_year : filings.new.fiscal_year) : null;
        const year = ref ? (ref.side === "old" ? "Last year" : "This year") : null;
        return (
          <li key={`${id}-${i}`} className="border-l-2 border-line pl-3 text-sm">
            <div className="mb-1 flex items-center justify-between gap-2 text-sm">
              <span className="text-ink-secondary">{year ? `${year}, FY${fy}` : "Unknown sentence"}</span>
              <a
                href={`#s-${id}`}
                onClick={(e) => {
                  e.preventDefault();
                  jumpTo(id, e.currentTarget);
                }}
                className="text-accent underline"
              >
                Show in the filing text
              </a>
            </div>
            <p className="font-serif text-base leading-relaxed text-ink">{ref ? ref.text : "Sentence not found."}</p>
          </li>
        );
      })}
    </ol>
  );
}

/** Score-line details worth showing to a general reader (others stay in Analyst details). */
const SHOW_DETAIL = new Set(["hypothetical_to_actual", "new_entities", "new_quantities", "added_text_ratio"]);

function ScoreRow({ line, changeType, figures }: { line: ScoreLine; changeType: string; figures: FigureVariant }) {
  const [open, setOpen] = useState(false);
  const signal = line.signal;
  const isChangeType = signal === "change_type" || signal.startsWith("change_type:");
  const label = scoreLineLabel(signal, changeType, line.label, figures);
  const helper = scoreLineHelper(signal, changeType, figures);
  const detail = line.detail && (SHOW_DETAIL.has(signal) || isChangeType) ? line.detail : null;
  const n = line.cited_sentence_ids.length;
  return (
    <li className="border-b border-line last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="grid w-full grid-cols-[18px_minmax(0,1fr)_56px] items-start gap-3 px-1 py-3 text-left hover:bg-paper"
      >
        <span aria-hidden="true" className={`pt-0.5 text-sm text-ink-secondary transition ${open ? "rotate-90" : ""}`}>
          ▸
        </span>
        <span className="min-w-0">
          <span className="block font-medium leading-snug text-ink" title={helper || undefined}>
            {label}
          </span>
          {detail ? <span className="mt-0.5 block text-sm leading-snug text-ink-secondary">{detail}</span> : null}
          <span className="mt-1 block text-sm text-accent">
            {open ? "Hide" : "Show"} {n} cited {n === 1 ? "sentence" : "sentences"}
          </span>
        </span>
        <span className="text-right text-base font-medium text-ink">
          {line.points > 0 ? "+" : ""}
          {line.points}
        </span>
      </button>
      {open ? (
        <div className="pb-4 pl-8">
          <CitedSentenceList ids={line.cited_sentence_ids} />
        </div>
      ) : null}
    </li>
  );
}

export function ScoreBreakdownPanel({ change }: { change: Change }) {
  const total = change.score_breakdown.reduce((s, l) => s + l.points, 0);
  const figures = figureVariant(change.signals.new_quantities);
  return (
    <section aria-labelledby="score-heading" className="space-y-3">
      <SectionTitle id="score-heading" aside={<ChangeLevel score={change.score} changeType={change.change_type} />}>
        How this was scored
      </SectionTitle>
      <p className="max-w-prose-72 text-sm text-ink-secondary">
        The wording-change level adds up fixed, published points for each thing that changed. {CHANGE_LEVEL.helper}
      </p>
      {change.score_breakdown.length === 0 ? (
        <p className="mt-3 text-ink-secondary">Nothing in this risk factor changed enough to add points.</p>
      ) : (
        <>
          <ul className="mt-3">
            {change.score_breakdown.map((line, i) => (
              <ScoreRow key={`${line.signal}-${i}`} line={line} changeType={change.change_type} figures={figures} />
            ))}
          </ul>
          <div className="mt-1 flex items-center justify-between border-t border-ink px-1 pt-2">
            <span className="font-medium text-ink">
              {total > 100 ? `Total, capped at 100 (points add to ${total})` : "Total"}: {CHANGE_LEVEL.prefix} {changeLevel(change.score)}
            </span>
            <span className="text-base font-medium text-ink">{change.score}</span>
          </div>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// Analyst details (collapsed by default)
// ---------------------------------------------------------------------------------------

/** Defense in depth: never echo a quoted phrase from a validator reason into the UI. */
function redactQuoted(reason: string): string {
  return reason.replace(/\((['"‘’“”])[^)]*\1\)/g, "(redacted)");
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-medium text-ink-secondary">{children}</h3>;
}

function HitList({ title, hits, numberOf }: { title: string; hits: SignalHit[]; numberOf: (id: string) => number }) {
  if (hits.length === 0) return null;
  return (
    <div>
      <SubHeading>{title}</SubHeading>
      <ul className="mt-1.5 space-y-2">
        {hits.map((h, i) => (
          <li key={i} className="text-sm">
            <p className="font-medium text-ink">{h.value}</p>
            {h.detail ? <p className="text-sm text-ink-secondary">{h.detail}</p> : null}
            <div className="mt-1">
              <CitationChips ids={[...(h.old_sentence_ids ?? []), ...(h.new_sentence_ids ?? [])]} withSide numberOf={numberOf} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RubricList({ interp, numberOf }: { interp: Interpretation; numberOf: (id: string) => number }) {
  const rubric = interp.rubric ?? [];
  if (rubric.length === 0) return <p className="text-sm text-ink-secondary">No AI rubric answers for this change ({interp.status}).</p>;
  return (
    <ul className="space-y-2.5">
      {rubric.map((r) => (
        <li key={r.question_id} className="border-l-2 border-line pl-3 text-sm">
          <div className="flex items-start gap-2">
            <span className="text-ink-secondary">{r.question_id}</span>
            <p className="min-w-0 flex-1 leading-snug text-ink">{r.question}</p>
            <span className={`shrink-0 rounded-sm px-1.5 py-px text-xs font-medium ${r.answer ? "bg-ink text-on-ink" : "bg-signal-bg text-ink-secondary"}`}>
              {r.answer ? "Yes" : "No"}
            </span>
          </div>
          {r.raw_answer === true && !r.answer ? (
            <p className="mt-1 text-sm text-actual-fg">The model answered yes without a valid citation, so it counts as no.</p>
          ) : null}
          {r.rationale ? <p className="mt-1 text-sm text-ink-secondary">{r.rationale}</p> : null}
          {(r.cited_sentence_ids ?? []).length > 0 ? (
            <div className="mt-1.5">
              <CitationChips ids={r.cited_sentence_ids ?? []} numberOf={numberOf} withSide />
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function AnalystDetails({
  change,
  numberOf,
  modelIds,
}: {
  change: Change;
  numberOf: (id: string) => number;
  modelIds: ModelIds;
}) {
  const s: Signals = change.signals;
  const interp = change.interpretation;
  const hedge = s.hypothetical_to_actual ?? [];
  const ents = s.new_entities ?? [];
  const qty = s.new_quantities ?? [];
  const cats = Object.entries(s.category_scores ?? {}).sort((a, b) => b[1] - a[1]);
  const assigned = new Set<string>(change.categories);
  const dropped = interp.dropped_claim_count ?? 0;
  const reasons = interp.dropped_reasons ?? [];
  return (
    <details className="group border-t border-line pt-4">
      <summary className="flex cursor-pointer list-none items-baseline gap-3">
        <span aria-hidden="true" className="text-ink-secondary transition group-open:rotate-90">
          ▸
        </span>
        <span className="text-lg font-medium text-ink">{ANALYST_DETAILS}</span>
        <span className="text-sm text-ink-secondary">Rule-based signals, text measures, AI check answers, models</span>
      </summary>
      <div className="mt-6 grid gap-x-10 gap-y-6 min-[900px]:grid-cols-2">
        <div className="space-y-4">
          <h3 className="text-base font-medium text-ink">Deterministic signals (rule-based, no AI)</h3>
          <HitList title={SIGNAL_VOCAB.hypothetical_to_actual.label} hits={hedge} numberOf={numberOf} />
          <HitList title={SIGNAL_VOCAB.new_entities.label} hits={ents} numberOf={numberOf} />
          <HitList title={figureVocab(figureVariant(qty)).label} hits={qty} numberOf={numberOf} />
          {hedge.length + ents.length + qty.length === 0 ? (
            <p className="text-sm text-ink-secondary">No hedge, entity or quantity signals detected.</p>
          ) : null}
          <div>
            <SubHeading>Text measures</SubHeading>
            <dl className="mt-1.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
              <dt className="text-ink-secondary">Added text (share of new words)</dt>
              <dd className="text-right text-ink">{formatShare(s.added_text_ratio)}</dd>
              <dt className="text-ink-secondary">Removed text (share of old words)</dt>
              <dd className="text-right text-ink">{formatShare(s.removed_text_ratio)}</dd>
              <dt className="text-ink-secondary">Semantic shift (1 − similarity)</dt>
              <dd className="text-right text-ink">{formatRatio(s.semantic_shift)}</dd>
              <dt className="text-ink-secondary">Match similarity (heading / body)</dt>
              <dd className="text-right text-ink">
                {change.similarity == null ? "n/a (unmatched)" : formatRatio(change.similarity)}
                {change.heading_similarity != null || change.body_similarity != null
                  ? ` (${formatRatio(change.heading_similarity)} / ${formatRatio(change.body_similarity)})`
                  : ""}
              </dd>
              <dt className="text-ink-secondary">Sentences added / removed / modified / unchanged</dt>
              <dd className="text-right text-ink">
                {change.stats.added} / {change.stats.removed} / {change.stats.modified} / {change.stats.unchanged}
              </dd>
            </dl>
          </div>
          {cats.length > 0 ? (
            <div>
              <SubHeading>Category similarity</SubHeading>
              <dl className="mt-1.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
                {cats.map(([c, v]) => (
                  <div key={c} className="contents">
                    <dt className={assigned.has(c) ? "font-semibold text-ink" : "text-ink-secondary"}>
                      {categoryLabel(c)}
                      {assigned.has(c) ? <span className="text-sm text-ink-secondary"> (assigned)</span> : null}
                    </dt>
                    <dd className="text-right text-ink">{formatRatio(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
        </div>
        <div className="space-y-4">
          <h3 className="text-base font-medium text-ink">AI rubric questions (Q1 to Q4)</h3>
          <p className="text-sm text-ink-secondary">A yes counts only when it cites valid filing sentences.</p>
          <RubricList interp={interp} numberOf={numberOf} />
          <div className="rounded-md bg-signal-bg px-3 py-2 text-sm">
            <p className="font-medium text-ink">
              Citation validator: {dropped} AI {dropped === 1 ? "statement" : "statements"} removed
            </p>
            {reasons.length > 0 ? (
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-secondary">
                {reasons.map((r, i) => (
                  <li key={i}>{redactQuoted(r)}</li>
                ))}
              </ul>
            ) : null}
            {interp.status !== "ok" ? (
              <p className="mt-1 text-ink-secondary">
                AI stage status: <span className="font-mono">{interp.status}</span>
                {interp.reason ? ` (${interp.reason})` : ""}
              </p>
            ) : null}
          </div>
          <div>
            <SubHeading>Models</SubHeading>
            <dl className="mt-1.5 grid grid-cols-[140px_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
              <dt className="text-ink-secondary">Language model</dt>
              <dd className="break-words font-mono text-ink">{interp.model_id ?? modelIds.llm_model ?? "not used"}</dd>
              <dt className="text-ink-secondary">Embedding model</dt>
              <dd className="break-words font-mono text-ink">
                {modelIds.embedding_model} ({modelIds.embedding_backend})
              </dd>
              <dt className="text-ink-secondary">NER model</dt>
              <dd className="break-words font-mono text-ink">{modelIds.ner_model}</dd>
              <dt className="text-ink-secondary">Sentence splitter</dt>
              <dd className="break-words font-mono text-ink">{modelIds.sentence_splitter}</dd>
              <dt className="text-ink-secondary">Categories</dt>
              <dd className="break-words font-mono text-ink">{modelIds.category_method}</dd>
            </dl>
          </div>
        </div>
      </div>
    </details>
  );
}
