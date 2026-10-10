"use client";

import { useState } from "react";

import type { Change, Interpretation, ScoreLine, SignalHit, Signals } from "@/types/comparison";

import { CitationChips, useCitations } from "@/components/citations";
import { ScoreBar } from "@/components/ui";
import { AI_NOTE, SCORE_EXPLAINER } from "@/lib/copy";
import { categoryLabel, formatRatio, formatShare } from "@/lib/format";

function PanelHeading({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <h2 className="text-base font-bold text-ink">{children}</h2>
      {aside}
    </div>
  );
}

function CitedSentenceList({ ids }: { ids: string[] }) {
  const { index, filings, jumpTo } = useCitations();
  if (ids.length === 0) return <p className="text-sm text-ink-faint">No sentences cited.</p>;
  return (
    <ol className="space-y-2">
      {ids.map((id, i) => {
        const ref = index[id];
        const fy = ref ? (ref.side === "old" ? filings.old.fiscal_year : filings.new.fiscal_year) : null;
        return (
          <li key={`${id}-${i}`} className="rounded border border-line bg-paper p-2 text-sm">
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="font-semibold text-ink-muted">
                [{i + 1}] {fy ? `FY${fy} filing` : "Unknown sentence"}
              </span>
              <a
                href={`#s-${id}`}
                onClick={(e) => {
                  e.preventDefault();
                  jumpTo(id);
                }}
                className="font-semibold text-accent underline"
              >
                Jump to sentence <span aria-hidden="true">↓</span>
              </a>
            </div>
            <p className="font-serif leading-relaxed text-ink">{ref ? ref.text : <span className="font-mono">{id}</span>}</p>
          </li>
        );
      })}
    </ol>
  );
}

function ScoreRow({ line }: { line: ScoreLine }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-b border-line last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="grid w-full grid-cols-[16px_minmax(0,1fr)_44px] items-start gap-2 py-2.5 text-left hover:bg-paper"
      >
        <span aria-hidden="true" className={`pt-0.5 font-mono text-xs text-ink-faint transition ${open ? "rotate-90" : ""}`}>
          ▸
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold leading-snug text-ink">{line.label}</span>
          {line.detail ? <span className="mt-0.5 block text-xs leading-snug text-ink-muted">{line.detail}</span> : null}
          <span className="mt-0.5 block text-xs text-ink-faint">
            {line.cited_sentence_ids.length} cited {line.cited_sentence_ids.length === 1 ? "sentence" : "sentences"}
          </span>
        </span>
        <span className="text-right font-mono text-sm font-bold tabular-nums text-ink">
          {line.points > 0 ? "+" : ""}
          {line.points}
        </span>
      </button>
      {open ? (
        <div className="pb-3 pl-6">
          <CitedSentenceList ids={line.cited_sentence_ids} />
        </div>
      ) : null}
    </li>
  );
}

export function ScoreBreakdownPanel({ change }: { change: Change }) {
  const total = change.score_breakdown.reduce((s, l) => s + l.points, 0);
  return (
    <section aria-labelledby="score-heading" className="rounded-lg border border-line bg-surface p-4">
      <PanelHeading aside={<ScoreBar score={change.score} width="w-24" />}>
        <span id="score-heading">Score breakdown</span>
      </PanelHeading>
      <p className="mt-1 text-xs leading-snug text-ink-faint">{SCORE_EXPLAINER}</p>
      {change.score_breakdown.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">No scoring signals fired for this change.</p>
      ) : (
        <>
          <ul className="mt-2">
            {change.score_breakdown.map((line, i) => (
              <ScoreRow key={`${line.signal}-${i}`} line={line} />
            ))}
          </ul>
          <div className="mt-1 flex items-center justify-between border-t-2 border-ink pt-2 text-sm">
            <span className="font-semibold text-ink">Total{total > 100 ? " (capped at 100)" : ""}</span>
            <span className="font-mono font-bold tabular-nums text-ink">{change.score}</span>
          </div>
        </>
      )}
    </section>
  );
}

const STATUS_TEXT: Record<string, string> = {
  unavailable: "AI interpretation unavailable",
  skipped: "AI interpretation skipped",
  empty: "No validated AI claims",
};

function Transparency({ interp }: { interp: Interpretation }) {
  const count = interp.dropped_claim_count ?? 0;
  const reasons = interp.dropped_reasons ?? [];
  return (
    <details className="mt-3 rounded border border-ai-line/40 bg-surface/70 px-3 py-2 text-xs">
      <summary className="cursor-pointer font-semibold text-ai-fg">
        Transparency: {count} {count === 1 ? "claim" : "claims"} removed by the citation validator
      </summary>
      {reasons.length > 0 ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-ink-muted">
          {reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-ink-muted">No claims were removed.</p>
      )}
      {interp.model_id ? (
        <p className="mt-2 text-ink-faint">
          Model: <span className="font-mono">{interp.model_id}</span>
        </p>
      ) : null}
    </details>
  );
}

export function AiInterpretationPanel({ interp }: { interp: Interpretation }) {
  const claims = interp.claims ?? [];
  const rubric = interp.rubric ?? [];
  return (
    <section
      aria-labelledby="ai-heading"
      className="rounded-lg border-2 border-dashed border-ai-line bg-ai-bg p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id="ai-heading" className="inline-flex items-center gap-1.5 rounded bg-ai-fg px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-white">
          <span aria-hidden="true">✦</span> AI interpretation
        </h2>
        {interp.status === "ok" && interp.model_id ? (
          <span className="truncate font-mono text-xs text-ai-fg" title={interp.model_id}>
            {interp.model_id}
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-xs leading-snug text-ai-fg">{AI_NOTE}</p>

      {interp.status !== "ok" ? (
        <div className="mt-3 rounded border border-ai-line/50 bg-surface p-3 text-sm">
          <p className="font-semibold text-ink">{STATUS_TEXT[interp.status] ?? interp.status}</p>
          <p className="mt-1 text-ink-muted">{interp.reason ?? "No reason recorded."}</p>
        </div>
      ) : null}

      {claims.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-xs font-bold uppercase tracking-wide text-ai-fg">Claims</h3>
          <ol className="mt-2 space-y-3">
            {claims.map((c, i) => (
              <li key={i} className="text-sm leading-relaxed text-ink">
                <p>{c.text}</p>
                <div className="mt-1">
                  <CitationChips ids={c.cited_sentence_ids} />
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : interp.status === "ok" ? (
        <p className="mt-3 text-sm text-ink-muted">The model returned no claims for this change.</p>
      ) : null}

      {rubric.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-xs font-bold uppercase tracking-wide text-ai-fg">Rubric answers</h3>
          <ul className="mt-2 space-y-2.5">
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
                    <CitationChips ids={r.cited_sentence_ids ?? []} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <Transparency interp={interp} />
    </section>
  );
}

function HitList({ title, hits }: { title: string; hits: SignalHit[] }) {
  if (hits.length === 0) return null;
  return (
    <div>
      <h3 className="text-xs font-bold uppercase tracking-wide text-ink-faint">{title}</h3>
      <ul className="mt-1.5 space-y-2">
        {hits.map((h, i) => {
          const oldIds = h.old_sentence_ids ?? [];
          const newIds = h.new_sentence_ids ?? [];
          return (
            <li key={i} className="text-sm">
              <p className="font-semibold text-ink">{h.value}</p>
              {h.detail ? <p className="text-xs text-ink-muted">{h.detail}</p> : null}
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <CitationChips ids={[...oldIds, ...newIds]} withSide />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SignalsPanel({ change }: { change: Change }) {
  const s: Signals = change.signals;
  const hedge = s.hypothetical_to_actual ?? [];
  const ents = s.new_entities ?? [];
  const qty = s.new_quantities ?? [];
  const cats = Object.entries(s.category_scores ?? {}).sort((a, b) => b[1] - a[1]);
  const assigned = new Set<string>(change.categories);
  return (
    <section aria-labelledby="signals-heading" className="rounded-lg border border-line bg-surface p-4">
      <PanelHeading aside={<span className="text-xs text-ink-faint">rule-based, no AI</span>}>
        <span id="signals-heading">Deterministic signals</span>
      </PanelHeading>
      <div className="mt-3 space-y-4">
        <HitList title="Hedged wording became actual wording" hits={hedge} />
        <HitList title="New named entities" hits={ents} />
        <HitList title="New quantities" hits={qty} />
        {hedge.length + ents.length + qty.length === 0 ? (
          <p className="text-sm text-ink-muted">No hedge, entity or quantity signals detected.</p>
        ) : null}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wide text-ink-faint">Text measures</h3>
          <dl className="mt-1.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
            <dt className="text-ink-muted">Added text (share of new words)</dt>
            <dd className="text-right font-mono tabular-nums text-ink">{formatShare(s.added_text_ratio)}</dd>
            <dt className="text-ink-muted">Removed text (share of old words)</dt>
            <dd className="text-right font-mono tabular-nums text-ink">{formatShare(s.removed_text_ratio)}</dd>
            <dt className="text-ink-muted">Semantic shift (1 − similarity)</dt>
            <dd className="text-right font-mono tabular-nums text-ink">{formatRatio(s.semantic_shift)}</dd>
          </dl>
        </div>
        {cats.length > 0 ? (
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wide text-ink-faint">Category similarity</h3>
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
    </section>
  );
}
