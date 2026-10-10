"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

import type { Change, DiffSpan, ModelIds, Sentence } from "@/types/comparison";

import { AnalystDetails, ScoreBreakdownPanel, WhatChangedPanel } from "@/components/ChangePanels";
import { CitationContext, changeCitationNumbering, type CitationApi, type FilingRef, type SentenceRef } from "@/components/citations";
import { MarkedText } from "@/components/MarkedText";
import { FilingLink, SectionTitle } from "@/components/ui";
import { pairDisplaySpans, rewrittenIds } from "@/lib/diffDisplay";
import { textFragmentUrl } from "@/lib/format";

type ViewMode = "split" | "inline";

/** Below this viewport width the diff opens in the inline view (side by side stays available). */
const NARROW_QUERY = "(max-width: 1099px)";

function subscribeNarrow(cb: () => void) {
  const m = window.matchMedia(NARROW_QUERY);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}
const narrowSnapshot = () => window.matchMedia(NARROW_QUERY).matches;
const narrowServerSnapshot = () => false;

const STATUS_META: Record<Sentence["status"] | "rewritten", { label: string }> = {
  added: { label: "Added" },
  removed: { label: "Removed" },
  modified: { label: "Edited" },
  rewritten: { label: "Rewritten" },
  unchanged: { label: "Unchanged" },
};

function SentenceBody({ s, heading, rewritten, spans }: { s: Sentence; heading: boolean; rewritten: boolean; spans: DiffSpan[] | null | undefined }) {
  const cls = `filing-text ${heading ? "is-heading" : ""} ${s.side === "old" ? "is-old" : ""} ${s.status === "unchanged" && !heading ? "is-unchanged" : ""}`;
  // A rewritten pair (most words changed) is drawn whole: last year struck, this year highlighted.
  const status = s.status === "modified" && rewritten ? (s.side === "old" ? "removed" : "added") : s.status;
  return (
    <p className={cls}>
      <MarkedText text={s.text} spans={spans} side={s.side} status={status} />
    </p>
  );
}

interface SentenceViewProps {
  s: Sentence;
  /** The spans to draw: the sentence's own, with case-only edits of its pair neutralized. */
  spans: DiffSpan[] | null | undefined;
  heading: boolean;
  rewritten: boolean;
  sideTag: string | null;
  highlighted: boolean;
  actionOpen: boolean;
  filing: FilingRef;
  isFixture: boolean;
  onCloseAction: () => void;
  onBack: (() => void) | null;
  /** Inline view: id of an identical unchanged old-side sentence shown merged into this one. */
  aliasId?: string;
  /** "stacked" (side by side): tag line above the text. "gutter" (inline): tag in a left gutter. */
  layout: "stacked" | "gutter";
  /** Inside a merged one-sided run the run's own line says "added" or "removed" once. */
  labelHidden?: boolean;
}

function SentenceView(props: SentenceViewProps) {
  if (!props.aliasId) return <SentenceInner {...props} />;
  // Keep an anchor for the merged old-side id so citations to it still resolve.
  return (
    <div id={`s-${props.aliasId}`} data-sentence-id={props.aliasId} tabIndex={-1} className="cite-target outline-none">
      <SentenceInner {...props} />
    </div>
  );
}

function StatusTag({ status, highlighted, sideTag }: { status: keyof typeof STATUS_META; highlighted: boolean; sideTag: string | null }) {
  const meta = STATUS_META[status];
  return (
    <>
      {highlighted ? <span className="font-medium text-ink">Cited</span> : null}
      {status !== "unchanged" ? <span>{meta.label}</span> : <span className="sr-only">Unchanged</span>}
      {sideTag ? <span>{sideTag}</span> : null}
    </>
  );
}

function SentenceInner({ s, spans, heading, rewritten, sideTag, highlighted, actionOpen, filing, isFixture, onCloseAction, onBack, layout, labelHidden = false }: SentenceViewProps) {
  const status: keyof typeof STATUS_META = s.status === "modified" && rewritten ? "rewritten" : s.status;
  const stacked = layout === "stacked";
  const showLabelLine = highlighted || (s.status !== "unchanged" && !labelHidden) || !!sideTag;
  const actions = actionOpen ? (
    <div
      role="group"
      aria-label="Cited sentence actions"
      className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-line bg-surface px-3 py-1.5 font-sans text-sm"
    >
      <FilingLink href={textFragmentUrl(filing.edgar_url, s.text)} isFixture={isFixture}>
        Open in SEC filing
      </FilingLink>
      <span className="text-ink-secondary">
        FY{filing.fiscal_year} {filing.form}
      </span>
      {onBack ? (
        <button type="button" onClick={onBack} className="ml-auto text-accent underline">
          Back to where you were
        </button>
      ) : null}
      <button type="button" onClick={onCloseAction} className={`${onBack ? "" : "ml-auto "}text-ink-secondary hover:text-ink`} aria-label="Close sentence actions">
        Close
      </button>
    </div>
  ) : null;
  const boxClass = `cite-target outline-none ${highlighted ? "cite-flash" : ""}`;

  if (stacked) {
    return (
      <div id={`s-${s.id}`} data-sentence-id={s.id} data-status={status} tabIndex={-1} className={`${boxClass} py-1.5 pr-2`}>
        {showLabelLine ? (
          <p className="mb-0.5 flex flex-wrap items-center gap-x-2.5 font-sans text-sm leading-tight text-ink-secondary">
            <StatusTag status={status} highlighted={highlighted} sideTag={sideTag} />
          </p>
        ) : (
          <span className="sr-only">Unchanged</span>
        )}
        <SentenceBody s={s} heading={heading} rewritten={rewritten} spans={spans} />
        {actions}
      </div>
    );
  }
  return (
    <div
      id={`s-${s.id}`}
      data-sentence-id={s.id}
      data-status={status}
      tabIndex={-1}
      className={`${boxClass} grid grid-cols-[96px_minmax(0,1fr)] gap-3 py-1.5 pl-2 pr-3`}
    >
      <div className="pt-1 font-sans text-sm leading-tight text-ink-secondary">
        <StatusTag status={status} highlighted={highlighted} sideTag={sideTag} />
      </div>
      <div className="min-w-0">
        <SentenceBody s={s} heading={heading} rewritten={rewritten} spans={spans} />
        {actions}
      </div>
    </div>
  );
}

/** One collapsed run of unchanged sentences, or the fold control above an opened run. */
function RunToggle({ count, open, onClick }: { count: number; open: boolean; onClick: () => void }) {
  const noun = count === 1 ? "unchanged sentence" : "unchanged sentences";
  return (
    <button type="button" aria-expanded={open} onClick={onClick} className="group my-1 flex w-full items-center gap-3 py-1 font-sans text-sm text-ink-secondary hover:text-ink">
      <span aria-hidden="true" className="h-px flex-1 bg-line" />
      <span>
        {open ? `Fold ${count} ${noun}` : `${count} ${noun}`}
        {!open ? <span className="ml-2 text-accent underline">show</span> : null}
      </span>
      <span aria-hidden="true" className="h-px flex-1 bg-line" />
    </button>
  );
}

// ---------------------------------------------------------------------------------------
// Layout model: rows (side by side) or sentences (inline), grouped into collapsible runs.
// ---------------------------------------------------------------------------------------

interface SplitRow {
  kind: "split";
  key: string;
  pair: number;
  old: Sentence[];
  new: Sentence[];
  collapsible: boolean;
  /** Set when 2+ consecutive one-sided rows (all added, or all removed) were merged into this one. */
  merged?: "added" | "removed";
}
interface InlineRow {
  kind: "inline";
  key: string;
  pair: number;
  s: Sentence;
  alias?: Sentence;
  collapsible: boolean;
}
type Row = SplitRow | InlineRow;
type Block<R extends Row> = { kind: "row"; row: R } | { kind: "run"; key: string; rows: R[]; count: number };

function rowIds(r: Row): string[] {
  return r.kind === "split" ? [...r.old, ...r.new].map((s) => s.id) : [r.s.id, ...(r.alias ? [r.alias.id] : [])];
}

/** "added" when only this year's side has sentences and all are added; "removed" for the mirror case. */
function oneSidedStatus(r: SplitRow): "added" | "removed" | null {
  if (r.old.length === 0 && r.new.length > 0 && r.new.every((s) => s.status === "added")) return "added";
  if (r.new.length === 0 && r.old.length > 0 && r.old.every((s) => s.status === "removed")) return "removed";
  return null;
}

/**
 * Side by side: a run of 2+ consecutive rows that are all added (or all removed) becomes one
 * row, so a long new passage shows one placeholder on the empty side instead of a wall of them.
 * Every sentence keeps its own row inside the merged cell (and its anchor id).
 */
function mergeOneSidedRuns(rows: SplitRow[]): SplitRow[] {
  const out: SplitRow[] = [];
  let i = 0;
  while (i < rows.length) {
    const status = rows[i].collapsible ? null : oneSidedStatus(rows[i]);
    let j = i + 1;
    if (status) while (j < rows.length && !rows[j].collapsible && oneSidedStatus(rows[j]) === status) j++;
    if (status && j - i >= 2) {
      const run = rows.slice(i, j);
      out.push({
        ...run[0],
        old: run.flatMap((r) => r.old),
        new: run.flatMap((r) => r.new),
        merged: status,
      });
    } else {
      out.push(...rows.slice(i, j));
    }
    i = j;
  }
  return out;
}

function groupRuns<R extends Row>(rows: R[]): Block<R>[] {
  const out: Block<R>[] = [];
  let run: R[] = [];
  const flush = () => {
    if (run.length > 0) out.push({ kind: "run", key: `run-${run[0].key}`, rows: run, count: new Set(run.map((r) => r.pair)).size });
    run = [];
  };
  for (const r of rows) {
    if (r.collapsible) run.push(r);
    else {
      flush();
      out.push({ kind: "row", row: r });
    }
  }
  flush();
  return out;
}

interface DetailProps {
  change: Change;
  index: Record<string, SentenceRef>;
  filings: { old: FilingRef; new: FilingRef };
  isFixture: boolean;
  modelIds: ModelIds;
}

export function ChangeDetail({ change, index, filings, isFixture, modelIds }: DetailProps) {
  const numberOf = changeCitationNumbering(change);
  const narrow = useSyncExternalStore(subscribeNarrow, narrowSnapshot, narrowServerSnapshot);
  const [chosenView, setChosenView] = useState<ViewMode | null>(null);
  const view: ViewMode = chosenView ?? (narrow ? "inline" : "split");
  const [allOpen, setAllOpen] = useState(false);
  const [openRuns, setOpenRuns] = useState<Set<string>>(() => new Set());
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const [returnEl, setReturnEl] = useState<HTMLElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const isHeading = useCallback((id: string) => index[id]?.is_heading === true || /:0$/.test(id), [index]);
  const rewritten = useMemo(() => rewrittenIds(change.sentences), [change.sentences]);
  const displaySpans = useMemo(() => pairDisplaySpans(change.sentences), [change.sentences]);

  const sorted = useMemo(
    () =>
      [...change.sentences].sort(
        (a, b) => a.pair_index - b.pair_index || (a.side === b.side ? 0 : a.side === "old" ? -1 : 1),
      ),
    [change.sentences],
  );
  const oldCount = change.sentences.filter((s) => s.side === "old").length;
  const newCount = change.sentences.length - oldCount;
  const oneSided = oldCount === 0 || newCount === 0;

  const blocks = useMemo((): Block<Row>[] => {
    const quiet = (s: Sentence) => s.status === "unchanged" && !isHeading(s.id);
    if (view === "split" && !oneSided) {
      const pairs = new Map<number, { old: Sentence[]; new: Sentence[] }>();
      for (const s of sorted) {
        const p = pairs.get(s.pair_index) ?? { old: [], new: [] };
        p[s.side].push(s);
        pairs.set(s.pair_index, p);
      }
      const rows: SplitRow[] = [...pairs.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([pi, p]) => ({ kind: "split", key: `p${pi}`, pair: pi, old: p.old, new: p.new, collapsible: [...p.old, ...p.new].every(quiet) }));
      return groupRuns<Row>(mergeOneSidedRuns(rows));
    }
    // Inline (and one-sided) view: an unchanged pair whose two sentences are byte-identical is
    // shown once, like a context line in a unified diff; the old id stays addressable.
    const byId = new Map(change.sentences.map((s) => [s.id, s] as const));
    const identicalOld = (s: Sentence) => {
      if (s.status !== "unchanged" || s.side !== "new" || !s.counterpart_id) return undefined;
      const o = byId.get(s.counterpart_id);
      return o && o.side === "old" && o.status === "unchanged" && o.text === s.text ? o : undefined;
    };
    const merged = new Set<string>();
    for (const s of change.sentences) {
      const o = identicalOld(s);
      if (o) merged.add(o.id);
    }
    const rows: InlineRow[] = sorted
      .filter((s) => !merged.has(s.id))
      .map((s) => ({ kind: "inline", key: s.id, pair: s.pair_index, s, alias: identicalOld(s), collapsible: quiet(s) }));
    return groupRuns<Row>(rows);
  }, [view, oneSided, sorted, change.sentences, isHeading]);

  const runOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const b of blocks) if (b.kind === "run") for (const r of b.rows) for (const id of rowIds(r)) m.set(id, b.key);
    return m;
  }, [blocks]);

  const isRunOpen = useCallback((key: string) => allOpen || openRuns.has(key), [allOpen, openRuns]);
  const toggleRun = (key: string) => {
    if (!isRunOpen(key)) {
      setOpenRuns((prev) => new Set(prev).add(key));
    } else if (allOpen) {
      // Folding one run while "show all" is on: switch to per-run state with the others open.
      setAllOpen(false);
      setOpenRuns(new Set(blocks.filter((b) => b.kind === "run" && b.key !== key).map((b) => (b.kind === "run" ? b.key : ""))));
    } else {
      setOpenRuns((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  const jumpTo = useCallback(
    (id: string, source?: HTMLElement | null) => {
      const sentence = change.sentences.find((s) => s.id === id);
      if (!sentence) {
        setMissing(id);
        return;
      }
      setMissing(null);
      const run = runOf.get(id);
      if (run && !isRunOpen(run)) {
        flushSync(() => setOpenRuns((prev) => new Set(prev).add(run)));
      }
      flushSync(() => {
        setHighlightId(id);
        setActionId(id);
        setReturnEl(source ?? null);
      });
      const el = document.getElementById(`s-${id}`);
      if (!el) return;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      el.focus({ preventScroll: true });
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setHighlightId(null), 3000);
    },
    [change.sentences, runOf, isRunOpen],
  );

  const api: CitationApi = useMemo(() => ({ index, filings, isFixture, jumpTo }), [index, filings, isFixture, jumpTo]);

  const yearTag = (side: Sentence["side"]) => (side === "old" ? `Last year, FY${filings.old.fiscal_year}` : `This year, FY${filings.new.fiscal_year}`);

  const renderSentence = (s: Sentence, withSideTag: boolean, aliasId?: string, labelHidden = false) => (
    <SentenceView
      key={s.id}
      s={s}
      spans={displaySpans.has(s.id) ? displaySpans.get(s.id) : s.diff_spans}
      layout={view === "split" ? "stacked" : "gutter"}
      labelHidden={labelHidden}
      aliasId={aliasId}
      heading={isHeading(s.id)}
      rewritten={rewritten.has(s.id)}
      sideTag={aliasId ? "Both years" : withSideTag ? yearTag(s.side) : null}
      highlighted={highlightId === s.id || (!!aliasId && highlightId === aliasId)}
      actionOpen={actionId === s.id || (!!aliasId && actionId === aliasId)}
      filing={(aliasId && actionId === aliasId) || s.side === "old" ? filings.old : filings.new}
      isFixture={isFixture}
      onCloseAction={() => setActionId(null)}
      onBack={
        returnEl
          ? () => {
              returnEl.scrollIntoView({ block: "center" });
              returnEl.focus({ preventScroll: true });
              setActionId(null);
            }
          : null
      }
    />
  );

  const emptyCell = (side: "old" | "new", merged?: { status: "added" | "removed"; count: number }) => {
    const label = merged
      ? merged.status === "added"
        ? `No sentences last year. ${merged.count} added this year.`
        : `No sentences this year. ${merged.count} removed.`
      : side === "old"
        ? "No sentence last year"
        : "No sentence this year";
    return (
      <div className="flex h-full min-h-8 items-start p-1.5">
        <span className={`font-sans text-sm text-ink-muted ${merged ? "sticky top-28" : ""}`}>{label}</span>
      </div>
    );
  };

  const renderRow = (r: Row) => {
    if (r.kind !== "split") return renderSentence(r.s, view === "inline", r.alias?.id);
    const merged = r.merged ? { status: r.merged, count: r.merged === "added" ? r.new.length : r.old.length } : undefined;
    if (merged) {
      // A run of sentences that exist on one side only: full width, with one line saying so,
      // instead of a column of text beside a column of nothing.
      const list = merged.status === "added" ? r.new : r.old;
      const noun = merged.count === 1 ? "sentence" : "sentences";
      const note =
        merged.status === "added"
          ? `${merged.count} ${noun} added this year. Nothing to compare in last year's filing.`
          : `${merged.count} ${noun} removed this year. Nothing to compare in this year's filing.`;
      return (
        <div key={r.key} className="border-y border-line py-2" data-merged-run={r.merged}>
          <p className="mb-1 font-sans text-sm text-ink-secondary">{note}</p>
          <div className="space-y-1">{list.map((s) => renderSentence(s, false, undefined, true))}</div>
        </div>
      );
    }
    return (
      <div key={r.key} className="grid grid-cols-2 gap-5" data-merged-run={r.merged}>
        <div className="space-y-1">{r.old.length ? r.old.map((s) => renderSentence(s, false)) : emptyCell("old", merged)}</div>
        <div className="space-y-1">{r.new.length ? r.new.map((s) => renderSentence(s, false)) : emptyCell("new", merged)}</div>
      </div>
    );
  };

  const renderBlocks = () =>
    blocks.map((b) => {
      if (b.kind === "row") return renderRow(b.row);
      const open = isRunOpen(b.key);
      return (
        <div key={b.key}>
          <RunToggle count={b.count} open={open} onClick={() => toggleRun(b.key)} />
          {open ? <div className="space-y-1">{b.rows.map(renderRow)}</div> : null}
        </div>
      );
    });

  const runCount = blocks.filter((b) => b.kind === "run").length;
  const anyClosed = blocks.some((b) => b.kind === "run" && !isRunOpen(b.key));

  function renderDiff() {
    if (view === "split") {
      const header = (
        <div
          className={`sticky ${isFixture ? "top-[96px]" : "top-14"} z-10 grid grid-cols-2 gap-5 border-b border-line bg-paper pb-2 pt-1 text-sm text-ink-secondary`}
        >
          <span>
            Last year, FY{filings.old.fiscal_year} {filings.old.form}
          </span>
          <span>
            This year, FY{filings.new.fiscal_year} {filings.new.form}
          </span>
        </div>
      );
      if (oneSided) {
        const absentOld = oldCount === 0;
        const absentBox = (
          <div className="min-h-[120px] p-1.5 text-base text-ink-muted">
            <p>{absentOld ? "Not in last year's filing." : "Removed this year."}</p>
          </div>
        );
        const presentCol = <div className="space-y-1">{renderBlocks()}</div>;
        return (
          <div className="split-view">
            {header}
            <div className="mt-2 grid grid-cols-2 gap-5">
              {absentOld ? absentBox : presentCol}
              {absentOld ? presentCol : absentBox}
            </div>
          </div>
        );
      }
      return (
        <div className="split-view">
          {header}
          <div className="mt-2 space-y-1">{renderBlocks()}</div>
        </div>
      );
    }
    // Line-length cap for the inline view: ~75 characters of filing text per line.
    return <div className="max-w-[calc(36rem+118px)] space-y-1">{renderBlocks()}</div>;
  }

  const missingRef = missing ? index[missing] : null;

  return (
    <CitationContext.Provider value={api}>
      <div className="space-y-10">
        <WhatChangedPanel interp={change.interpretation} numberOf={numberOf} />

        <section aria-labelledby="diff-heading" className="min-w-0 space-y-4">
          <SectionTitle
            id="diff-heading"
            aside={
              <span className="flex flex-wrap items-center gap-x-5 gap-y-1" aria-label="Legend">
                <span>
                  <mark className="hl">new words</mark>
                </span>
                <span>
                  <del className="strike">removed words</del>
                </span>
              </span>
            }
          >
            Sentence by sentence
          </SectionTitle>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <p className="text-sm text-ink-secondary">Changed sentences only. {runCount > 0 ? "Unchanged text is folded." : ""}</p>
            <div role="group" aria-label="Diff layout" className="inline-flex rounded-md border border-line p-0.5">
              {(
                [
                  ["split", "Side by side"],
                  ["inline", "Inline"],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={view === mode}
                  onClick={() => setChosenView(mode)}
                  className={`rounded-sm px-3 py-1 text-sm ${view === mode ? "bg-ink text-on-ink" : "text-ink-secondary hover:text-ink"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            {runCount > 0 ? (
              <button
                type="button"
                onClick={() => {
                  if (anyClosed) setAllOpen(true);
                  else {
                    setAllOpen(false);
                    setOpenRuns(new Set());
                  }
                }}
                className="text-sm text-accent underline underline-offset-2"
              >
                {anyClosed ? "Show all unchanged sentences" : "Fold all unchanged sentences"}
              </button>
            ) : null}
          </div>
          {change.sentences.length === 0 ? <p className="text-ink-secondary">No sentences recorded for this change.</p> : renderDiff()}
        </section>

        <ScoreBreakdownPanel change={change} />

        <AnalystDetails change={change} numberOf={numberOf} modelIds={modelIds} />
      </div>

      {missing ? (
        <div role="status" className="fixed bottom-6 right-6 z-50 w-[420px] max-w-[calc(100vw-48px)] rounded-md border border-line bg-surface p-4 text-sm text-ink shadow-card">
          <p className="font-medium">That cited sentence is not part of this risk factor&apos;s text.</p>
          {missingRef ? <p className="mt-1 font-serif text-base text-ink">{missingRef.text}</p> : null}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            {missingRef ? (
              <FilingLink href={textFragmentUrl(filings[missingRef.side].edgar_url, missingRef.text)} isFixture={isFixture}>
                Open in SEC filing (FY{filings[missingRef.side].fiscal_year})
              </FilingLink>
            ) : null}
            <button type="button" className="underline" onClick={() => setMissing(null)}>
              Dismiss
            </button>
          </div>
        </div>
      ) : null}
    </CitationContext.Provider>
  );
}
