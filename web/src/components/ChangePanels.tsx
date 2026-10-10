"use client";

import { useState } from "react";

import type { Change, Interpretation, ModelIds, ScoreLine, SignalHit, Signals } from "@/types/comparison";

import { CitationChips, useCitations } from "@/components/citations";
import { ChangeLevelTag } from "@/components/ui";
import { categoryLabel, formatRatio, formatShare } from "@/lib/format";
import {
  AI_SUMMARY,
  ANALYST_DETAILS,
  CHANGE_LEVEL,
  changeLevel,
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
    <section aria-labelledby="what-changed-heading" className="space-y-2">
      <h2 id="what-changed-heading" className="text-xl font-bold text-ink">
        What changed
      </h2>
      {claims.length === 0 ? (
        <p className="text-ink-muted">No AI summary for this change.</p>
      ) : (
        <div className="rounded-lg border-2 border-dashed border-ai-line bg-ai-bg p-5">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded bg-ai-fg px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-white">
              <span aria-hidden="true">✦</span> {AI_SUMMARY.label}
            </span>
            <span className="text-sm font-medium text-ai-fg">every point cites the filing</span>
          </p>
          <ul className="mt-3 space-y-3">
            {claims.map((c, i) => (
              <li key={i} className="flex gap-3 text-base leading-relaxed text-ink">
                <span aria-hidden="true" className="pt-0.5 font-bold text-ai-fg">
                  •
                </span>
                <span className="min-w-0">
                  {c.text} <CitationChips ids={c.cited_sentence_ids} numberOf={numberOf} withSide />
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ai-fg">{AI_SUMMARY.helper} Click a number to see the sentence in the filing text below.</p>
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
  if (ids.length === 0) return <p className="text-sm text-ink-faint">No sentences cited.</p>;
  return (
    <ol className="space-y-2">
      {ids.map((id, i) => {
        const ref = index[id];
        const fy = ref ? (ref.side === "old" ? filings.old.fiscal_year : filings.new.fiscal_year) : null;
        const year = ref ? (ref.side === "old" ? "Last year" : "This year") : null;
        return (
          <li key={`${id}-${i}`} className="rounded border border-line bg-paper p-3 text-sm">
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="font-semibold text-ink-muted">{year ? `${year} · FY${fy}` : "Unknown sentence"}</span>
              <a
                href={`#s-${id}`}
                onClick={(e) => {
                  e.preventDefault();
                  jumpTo(id, e.currentTarget);
                }}
                className="font-semibold text-accent underline"
              >
                Show in the filing text <span aria-hidden="true">↑</span>
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

function ScoreRow({ line, changeType }: { line: ScoreLine; changeType: string }) {
  const [open, setOpen] = useState(false);
  const signal = line.signal;
  const isChangeType = signal === "change_type" || signal.startsWith("change_type:");
  const label = scoreLineLabel(signal, changeType, line.label);
  const helper = scoreLineHelper(signal, changeType);
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
        <span aria-hidden="true" className={`pt-0.5 font-mono text-sm text-ink-faint transition ${open ? "rotate-90" : ""}`}>
          ▸
        </span>
        <span className="min-w-0">
          <span className="block font-semibold leading-snug text-ink">{label}</span>
          {detail ? <span className="mt-0.5 block text-sm leading-snug text-ink">{detail}</span> : null}
          {helper ? <span className="mt-0.5 block text-sm leading-snug text-ink-faint">{helper}</span> : null}
          <span className="mt-1 block text-xs font-medium text-accent">
            {open ? "Hide" : "Show"} {n} cited {n === 1 ? "sentence" : "sentences"}
          </span>
        </span>
        <span className="text-right font-mono text-base font-bold tabular-nums text-ink">
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
  return (
    <section aria-labelledby="score-heading" className="rounded-lg border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="score-heading" className="text-xl font-bold text-ink">
          How this was scored
        </h2>
        <ChangeLevelTag score={change.score} withCaption />
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        {CHANGE_LEVEL.label} adds up fixed, published points for each thing that changed. {CHANGE_LEVEL.helper}
      </p>
      {change.score_breakdown.length === 0 ? (
        <p className="mt-3 text-ink-muted">Nothing in this risk factor changed enough to add points.</p>
      ) : (
        <>
          <ul className="mt-3">
            {change.score_breakdown.map((line, i) => (
              <ScoreRow key={`${line.signal}-${i}`} line={line} changeType={change.change_type} />
            ))}
          </ul>
          <div className="mt-1 flex items-center justify-between border-t-2 border-ink px-1 pt-2">
            <span className="font-semibold text-ink">
              Total{total > 100 ? " (capped at 100)" : ""} · {changeLevel(change.score)}
            </span>
            <span className="font-mono text-base font-bold tabular-nums text-ink">{change.score}</span>
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
  return <h3 className="text-xs font-bold uppercase tracking-wide text-ink-faint">{children}</h3>;
}

function HitList({ title, hits, numberOf }: { title: string; hits: SignalHit[]; numberOf: (id: string) => number }) {
  if (hits.length === 0) return null;
  return (
    <div>
      <SubHeading>{title}</SubHeading>
      <ul className="mt-1.5 space-y-2">
        {hits.map((h, i) => (
          <li key={i} className="text-sm">
            <p className="font-semibold text-ink">{h.value}</p>
            {h.detail ? <p className="text-xs text-ink-muted">{h.detail}</p> : null}
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
  if (rubric.length === 0) return <p className="text-sm text-ink-muted">No AI rubric answers for this change ({interp.status}).</p>;
  return (
    <ul className="space-y-2.5">
      {rubric.map((r) => (
        <li key={r.question_id} className="rounded border border-ai-line/30 bg-surface p-2.5 text-sm">
          <div className="flex items-start gap-2">
            <span className="font-mono text-xs font-bold text-ai-fg">{r.question_id}</span>
            <p className="min-w-0 flex-1 leading-snug text-ink">{r.question}</p>
            <span
              className={`shrink-0 rounded border px-1.5 py-px text-xs font-bold ${
                r.answer ? "border-ink bg-ink text-white" : "border-line-strong bg-surface text-ink-muted"
              }`}
            >
              {r.answer ? "✓ Yes" : "✕ No"}
            </span>
          </div>
          {r.raw_answer === true && !r.answer ? (
            <p className="mt-1 text-xs text-mod-fg">The model answered yes without a valid citation, so it counts as no.</p>
          ) : null}
          {r.rationale ? <p className="mt-1 text-xs text-ink-muted">{r.rationale}</p> : null}
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
    <details className="group rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-4">
        <span aria-hidden="true" className="font-mono text-ink-faint transition group-open:rotate-90">
          ▸
        </span>
        <span className="text-lg font-bold text-ink">{ANALYST_DETAILS}</span>
        <span className="text-sm text-ink-faint">rule-based signals, measures, AI rubric and models</span>
      </summary>
      <div className="grid grid-cols-2 gap-x-10 gap-y-6 border-t border-line px-5 py-5">
        <div className="space-y-4">
          <h3 className="text-base font-bold text-ink">Deterministic signals (rule-based, no AI)</h3>
          <HitList title={SIGNAL_VOCAB.hypothetical_to_actual.label} hits={hedge} numberOf={numberOf} />
          <HitList title={SIGNAL_VOCAB.new_entities.label} hits={ents} numberOf={numberOf} />
          <HitList title={SIGNAL_VOCAB.new_quantities.label} hits={qty} numberOf={numberOf} />
          {hedge.length + ents.length + qty.length === 0 ? (
            <p className="text-sm text-ink-muted">No hedge, entity or quantity signals detected.</p>
          ) : null}
          <div>
            <SubHeading>Text measures</SubHeading>
            <dl className="mt-1.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
              <dt className="text-ink-muted">Added text (share of new words)</dt>
              <dd className="text-right font-mono tabular-nums text-ink">{formatShare(s.added_text_ratio)}</dd>
              <dt className="text-ink-muted">Removed text (share of old words)</dt>
              <dd className="text-right font-mono tabular-nums text-ink">{formatShare(s.removed_text_ratio)}</dd>
              <dt className="text-ink-muted">Semantic shift (1 − similarity)</dt>
              <dd className="text-right font-mono tabular-nums text-ink">{formatRatio(s.semantic_shift)}</dd>
              <dt className="text-ink-muted">Match similarity (heading / body)</dt>
              <dd className="text-right font-mono tabular-nums text-ink">
                {change.similarity == null ? "n/a (unmatched)" : formatRatio(change.similarity)}
                {change.heading_similarity != null || change.body_similarity != null
                  ? ` (${formatRatio(change.heading_similarity)} / ${formatRatio(change.body_similarity)})`
                  : ""}
              </dd>
              <dt className="text-ink-muted">Sentences added / removed / modified / unchanged</dt>
              <dd className="text-right font-mono tabular-nums text-ink">
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
                    <dt className={assigned.has(c) ? "font-semibold text-ink" : "text-ink-muted"}>
                      {categoryLabel(c)}
                      {assigned.has(c) ? <span className="text-xs font-normal text-ink-faint"> (assigned)</span> : null}
                    </dt>
                    <dd className="text-right font-mono tabular-nums text-ink">{formatRatio(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
        </div>
        <div className="space-y-4">
          <h3 className="text-base font-bold text-ink">AI rubric questions (Q1–Q4)</h3>
          <p className="text-sm text-ink-muted">A yes counts only when it cites valid filing sentences.</p>
          <RubricList interp={interp} numberOf={numberOf} />
          <div className="rounded border border-ai-line/40 bg-ai-bg px-3 py-2 text-sm">
            <p className="font-semibold text-ai-fg">
              Citation validator: {dropped} AI {dropped === 1 ? "statement" : "statements"} removed
            </p>
            {reasons.length > 0 ? (
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-muted">
                {reasons.map((r, i) => (
                  <li key={i}>{redactQuoted(r)}</li>
                ))}
              </ul>
            ) : null}
            {interp.status !== "ok" ? (
              <p className="mt-1 text-ink-muted">
                AI stage status: <span className="font-mono">{interp.status}</span>
                {interp.reason ? ` (${interp.reason})` : ""}
              </p>
            ) : null}
          </div>
          <div>
            <SubHeading>Models</SubHeading>
            <dl className="mt-1.5 grid grid-cols-[140px_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
              <dt className="text-ink-muted">Language model</dt>
              <dd className="break-words font-mono text-ink">{interp.model_id ?? modelIds.llm_model ?? "not used"}</dd>
              <dt className="text-ink-muted">Embedding model</dt>
              <dd className="break-words font-mono text-ink">
                {modelIds.embedding_model} ({modelIds.embedding_backend})
              </dd>
              <dt className="text-ink-muted">NER model</dt>
              <dd className="break-words font-mono text-ink">{modelIds.ner_model}</dd>
              <dt className="text-ink-muted">Sentence splitter</dt>
              <dd className="break-words font-mono text-ink">{modelIds.sentence_splitter}</dd>
              <dt className="text-ink-muted">Categories</dt>
              <dd className="break-words font-mono text-ink">{modelIds.category_method}</dd>
            </dl>
          </div>
        </div>
      </div>
    </details>
  );
}
