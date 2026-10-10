"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

import type { Change, ModelIds, Sentence } from "@/types/comparison";

import { AnalystDetails, ScoreBreakdownPanel, WhatChangedPanel } from "@/components/ChangePanels";
import { CitationContext, changeCitationNumbering, type CitationApi, type FilingRef, type SentenceRef } from "@/components/citations";
import { FilingLink } from "@/components/ui";
import { mergeChangedSpans, rewrittenIds } from "@/lib/diffDisplay";
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

const STATUS_META: Record<Sentence["status"] | "rewritten", { marker: string; label: string; border: string; gutter: string }> = {
  added: { marker: "+", label: "Added", border: "border-add-line", gutter: "text-add-fg" },
  removed: { marker: "−", label: "Removed", border: "border-del-line", gutter: "text-del-fg" },
  modified: { marker: "~", label: "Edited", border: "border-mod-line", gutter: "text-mod-fg" },
  rewritten: { marker: "~", label: "Rewritten", border: "border-mod-line", gutter: "text-mod-fg" },
  unchanged: { marker: "", label: "Unchanged", border: "border-transparent", gutter: "text-ink-faint" },
};

const STATUS_TINT: Record<string, string> = {
  added: "bg-add-bg/40",
  removed: "bg-del-bg/40",
};

/** Splits a span into leading whitespace, the marked core, and trailing whitespace. */
function splitWhitespace(text: string): [string, string, string] {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
  return m ? [m[1], m[2], m[3]] : ["", text, ""];
}

function SentenceBody({ s, heading, rewritten }: { s: Sentence; heading: boolean; rewritten: boolean }) {
  const cls = `filing-text ${heading ? "is-heading" : ""} ${s.status === "unchanged" && !heading ? "is-unchanged" : ""}`;
  if (s.status === "added") {
    return (
      <p className={cls}>
        <ins className="added-text no-underline">{s.text}</ins>
      </p>
    );
  }
  if (s.status === "removed") {
    return (
      <p className={cls}>
        <del className="removed-text">{s.text}</del>
      </p>
    );
  }
  if (s.status === "modified" && rewritten) {
    return (
      <p className={cls}>
        {s.side === "old" ? (
          <del className="rewritten-old">
            <span className="sr-only">deleted: </span>
            {s.text}
          </del>
        ) : (
          <ins className="rewritten-new">
            <span className="sr-only">inserted: </span>
            {s.text}
          </ins>
        )}
      </p>
    );
  }
  if (s.status === "modified" && s.diff_spans && s.diff_spans.length > 0) {
    return (
      <p className={cls}>
        {mergeChangedSpans(s.diff_spans).map((span, i) => {
          if (span.op !== "insert" && span.op !== "delete") return <span key={i}>{span.text}</span>;
          // Leading/trailing whitespace stays plain text so the marker sits right before the
          // first word and the underline/strikethrough never starts or ends on a space.
          const [lead, core, trail] = splitWhitespace(span.text);
          if (!core) return <span key={i}>{span.text}</span>;
          const insert = span.op === "insert";
          return (
            <span key={i}>
              {lead}
              <span aria-hidden="true" className={`span-mark ${insert ? "text-add-fg" : "text-del-fg"}`}>
                {insert ? "+" : "−"}
              </span>
              {insert ? (
                <ins className="span-ins">
                  <span className="sr-only">inserted: </span>
                  {core}
                </ins>
              ) : (
                <del className="span-del">
                  <span className="sr-only">deleted: </span>
                  {core}
                </del>
              )}
              {trail}
            </span>
          );
        })}
      </p>
    );
  }
  return <p className={cls}>{s.text}</p>;
}

interface SentenceViewProps {
  s: Sentence;
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

function StatusTag({ status, highlighted, sideTag, stacked }: { status: keyof typeof STATUS_META; highlighted: boolean; sideTag: string | null; stacked: boolean }) {
  const meta = STATUS_META[status];
  return (
    <>
      {highlighted ? (
        <span className={`${stacked ? "" : "mb-0.5 block "}font-bold text-ink`}>
          <span aria-hidden="true">▶ </span>Cited
        </span>
      ) : null}
      {status !== "unchanged" ? (
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="font-mono text-sm leading-none">
            {meta.marker}
          </span>
          {meta.label}
        </span>
      ) : (
        <span className="sr-only">Unchanged</span>
      )}
      {sideTag ? <span className={`${stacked ? "" : "mt-0.5 block "}font-medium text-ink-faint`}>{sideTag}</span> : null}
    </>
  );
}

function SentenceInner({ s, heading, rewritten, sideTag, highlighted, actionOpen, filing, isFixture, onCloseAction, onBack, layout }: SentenceViewProps) {
  const status: keyof typeof STATUS_META = s.status === "modified" && rewritten ? "rewritten" : s.status;
  const meta = STATUS_META[status];
  const stacked = layout === "stacked";
  const showLabelLine = highlighted || s.status !== "unchanged" || !!sideTag;
  const actions = actionOpen ? (
    <div
      role="group"
      aria-label="Cited sentence actions"
      className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-line-strong bg-surface px-3 py-1.5 font-sans text-sm shadow-sm"
    >
      <FilingLink href={textFragmentUrl(filing.edgar_url, s.text)} isFixture={isFixture} className="font-semibold">
        View in SEC filing
      </FilingLink>
      <span className="text-ink-faint">
        FY{filing.fiscal_year} {filing.form}
      </span>
      {onBack ? (
        <button type="button" onClick={onBack} className="ml-auto font-semibold text-accent underline">
          <span aria-hidden="true">↩ </span>Back to where you were
        </button>
      ) : null}
      <button
        type="button"
        onClick={onCloseAction}
        className={`${onBack ? "" : "ml-auto "}text-ink-muted hover:text-ink`}
        aria-label="Close sentence actions"
      >
        ✕
      </button>
    </div>
  ) : null;
  const boxClass = `cite-target rounded-r border-l-4 outline-none ${highlighted ? "cite-flash border-ink" : `${meta.border} ${STATUS_TINT[s.status] ?? ""}`}`;

  if (stacked) {
    return (
      <div id={`s-${s.id}`} data-sentence-id={s.id} data-status={status} tabIndex={-1} className={`${boxClass} py-1.5 pl-3 pr-2`}>
        {showLabelLine ? (
          <p className={`mb-0.5 flex flex-wrap items-center gap-x-2.5 font-sans text-xs font-semibold leading-tight ${meta.gutter}`}>
            <StatusTag status={status} highlighted={highlighted} sideTag={sideTag} stacked />
          </p>
        ) : (
          <span className="sr-only">Unchanged</span>
        )}
        <SentenceBody s={s} heading={heading} rewritten={rewritten} />
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
      className={`${boxClass} grid grid-cols-[84px_minmax(0,1fr)] gap-2.5 py-1.5 pl-2 pr-3`}
    >
      <div className={`pt-1 font-sans text-xs font-semibold leading-tight ${meta.gutter}`}>
        <StatusTag status={status} highlighted={highlighted} sideTag={sideTag} stacked={false} />
      </div>
      <div className="min-w-0">
        <SentenceBody s={s} heading={heading} rewritten={rewritten} />
        {actions}
      </div>
    </div>
  );
}

/** One collapsed run of unchanged sentences, or the "fold" control above an opened run. */
function RunToggle({ count, open, onClick }: { count: number; open: boolean; onClick: () => void }) {
  const noun = count === 1 ? "unchanged sentence" : "unchanged sentences";
  return (
    <button
      type="button"
      aria-expanded={open}
      onClick={onClick}
      className="group my-1 flex w-full items-center gap-3 py-1 font-sans text-sm text-ink-faint hover:text-ink"
    >
      <span aria-hidden="true" className="h-px flex-1 bg-line group-hover:bg-line-strong" />
      <span>
        {open ? (
          <>
            <span aria-hidden="true">▾ </span>Fold {count} {noun}
          </>
        ) : (
          <>
            <span aria-hidden="true">· </span>
            {count} {noun}
            <span aria-hidden="true"> ·</span>
            <span className="ml-2 font-semibold text-accent">show</span>
          </>
        )}
      </span>
      <span aria-hidden="true" className="h-px flex-1 bg-line group-hover:bg-line-strong" />
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
      return groupRuns<Row>(rows);
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

  const yearTag = (side: Sentence["side"]) =>
    side === "old" ? `Last year · FY${filings.old.fiscal_year}` : `This year · FY${filings.new.fiscal_year}`;

  const renderSentence = (s: Sentence, withSideTag: boolean, aliasId?: string) => (
    <SentenceView
      key={s.id}
      s={s}
      layout={view === "split" ? "stacked" : "gutter"}
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

  const emptyCell = (side: "old" | "new") => (
    <div className="h-full min-h-8 rounded border border-dashed border-line bg-[repeating-linear-gradient(135deg,transparent,transparent_6px,var(--color-sunken)_6px,var(--color-sunken)_12px)]">
      <span className="sr-only">No corresponding sentence in {side === "old" ? "last year's" : "this year's"} filing.</span>
    </div>
  );

  const renderRow = (r: Row) =>
    r.kind === "split" ? (
      <div key={r.key} className="grid grid-cols-2 gap-5">
        <div className="space-y-1">{r.old.length ? r.old.map((s) => renderSentence(s, false)) : emptyCell("old")}</div>
        <div className="space-y-1">{r.new.length ? r.new.map((s) => renderSentence(s, false)) : emptyCell("new")}</div>
      </div>
    ) : (
      renderSentence(r.s, view === "inline", r.alias?.id)
    );

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
          className={`sticky ${isFixture ? "top-[96px]" : "top-14"} z-10 grid grid-cols-2 gap-5 border-b border-line bg-surface pb-2 pt-1 text-xs font-semibold uppercase tracking-wide text-ink-faint`}
        >
          <span>
            Last year · FY{filings.old.fiscal_year} {filings.old.form}
          </span>
          <span>
            This year · FY{filings.new.fiscal_year} {filings.new.form}
          </span>
        </div>
      );
      if (oneSided) {
        const absentOld = oldCount === 0;
        const absentBox = (
          <div className="flex h-full min-h-[120px] items-start rounded border border-dashed border-line-strong bg-[repeating-linear-gradient(135deg,var(--color-paper),var(--color-paper)_8px,var(--color-sunken)_8px,var(--color-sunken)_16px)] p-4 text-base text-ink-muted">
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
      <div className="space-y-8">
        <WhatChangedPanel interp={change.interpretation} numberOf={numberOf} />

        <section aria-labelledby="diff-heading" className="min-w-0 rounded-lg border border-line bg-surface p-5">
          <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line pb-4">
            <div>
              <h2 id="diff-heading" className="text-xl font-bold text-ink">
                Sentence by sentence
              </h2>
              <p className="text-sm text-ink-muted">
                Changed sentences only. {runCount > 0 ? "Unchanged text is folded; click a fold to read it." : ""}
              </p>
            </div>
            <div role="group" aria-label="Diff layout" className="inline-flex rounded-md border border-line-strong p-0.5">
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
                  className={`rounded px-3 py-1 text-sm font-medium ${view === mode ? "bg-ink text-white" : "text-ink-muted hover:text-ink"}`}
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
                className="text-sm font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
              >
                {anyClosed ? "Show all unchanged sentences" : "Fold all unchanged sentences"}
              </button>
            ) : null}
            <ul className="ml-auto flex flex-wrap items-center gap-3 text-sm text-ink-muted" aria-label="Legend">
              <li>
                <span className="font-mono font-bold text-add-fg">+</span> <ins className="span-ins">added</ins>
              </li>
              <li>
                <span className="font-mono font-bold text-del-fg">−</span> <del className="span-del">removed</del>
              </li>
              <li>
                <span className="font-mono font-bold text-mod-fg">~</span> edited or rewritten
              </li>
            </ul>
          </div>
          {change.sentences.length === 0 ? <p className="text-ink-muted">No sentences recorded for this change.</p> : renderDiff()}
        </section>

        <ScoreBreakdownPanel change={change} />

        <AnalystDetails change={change} numberOf={numberOf} modelIds={modelIds} />
      </div>

      {missing ? (
        <div role="status" className="fixed bottom-6 right-6 z-50 w-[420px] max-w-[calc(100vw-48px)] rounded border border-mod-line bg-mod-bg p-4 text-sm text-mod-fg shadow-lg">
          <p className="font-semibold">That cited sentence is not part of this risk factor&apos;s text.</p>
          {missingRef ? <p className="mt-1 font-serif text-base text-ink">{missingRef.text}</p> : null}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            {missingRef ? (
              <FilingLink href={textFragmentUrl(filings[missingRef.side].edgar_url, missingRef.text)} isFixture={isFixture} className="font-semibold">
                View in SEC filing (FY{filings[missingRef.side].fiscal_year})
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
