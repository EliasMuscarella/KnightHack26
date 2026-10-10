"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";

import type { Change, Sentence } from "@/types/comparison";

import { AiInterpretationPanel, ScoreBreakdownPanel, SignalsPanel } from "@/components/ChangePanels";
import { CitationContext, type CitationApi, type FilingRef, type SentenceRef } from "@/components/citations";
import { textFragmentUrl } from "@/lib/format";

type ViewMode = "split" | "inline";

const STATUS_META: Record<
  Sentence["status"],
  { marker: string; label: string; border: string; gutter: string }
> = {
  added: { marker: "+", label: "Added", border: "border-add-line", gutter: "text-add-fg" },
  removed: { marker: "−", label: "Removed", border: "border-del-line", gutter: "text-del-fg" },
  modified: { marker: "~", label: "Modified", border: "border-mod-line", gutter: "text-mod-fg" },
  unchanged: { marker: "", label: "Unchanged", border: "border-transparent", gutter: "text-ink-faint" },
};

function SentenceBody({ s, heading }: { s: Sentence; heading: boolean }) {
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
  if (s.status === "modified" && s.diff_spans && s.diff_spans.length > 0) {
    return (
      <p className={cls}>
        {s.diff_spans.map((span, i) => {
          if (span.op === "insert") {
            return (
              <ins key={i} className="span-ins">
                <span aria-hidden="true" className="span-mark">
                  +
                </span>
                {span.text}
              </ins>
            );
          }
          if (span.op === "delete") {
            return (
              <del key={i} className="span-del">
                <span aria-hidden="true" className="span-mark">
                  −
                </span>
                {span.text}
              </del>
            );
          }
          return <span key={i}>{span.text}</span>;
        })}
      </p>
    );
  }
  return <p className={cls}>{s.text}</p>;
}

interface SentenceViewProps {
  s: Sentence;
  heading: boolean;
  sideTag: string | null;
  highlighted: boolean;
  actionOpen: boolean;
  filing: FilingRef;
  isFixture: boolean;
  onCloseAction: () => void;
}

function SentenceView({ s, heading, sideTag, highlighted, actionOpen, filing, isFixture, onCloseAction }: SentenceViewProps) {
  const meta = STATUS_META[s.status];
  return (
    <div
      id={`s-${s.id}`}
      data-sentence-id={s.id}
      data-status={s.status}
      tabIndex={-1}
      className={`cite-target grid grid-cols-[96px_minmax(0,1fr)] gap-3 rounded-r border-l-4 py-1.5 pl-2 pr-3 outline-none ${
        highlighted ? "cite-flash border-ink" : meta.border
      }`}
    >
      <div className={`pt-1 text-xs font-semibold leading-tight ${meta.gutter}`}>
        {highlighted ? (
          <span className="mb-0.5 block font-bold text-ink">
            <span aria-hidden="true">▶ </span>Cited
          </span>
        ) : null}
        {s.status !== "unchanged" ? (
          <span className="flex items-center gap-1">
            <span aria-hidden="true" className="font-mono text-sm">
              {meta.marker}
            </span>
            {meta.label}
          </span>
        ) : (
          <span className="sr-only">Unchanged</span>
        )}
        {sideTag ? <span className="mt-0.5 block font-mono font-medium text-ink-faint">{sideTag}</span> : null}
      </div>
      <div className="min-w-0">
        <SentenceBody s={s} heading={heading} />
        {actionOpen ? (
          <div
            role="group"
            aria-label="Cited sentence actions"
            className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-line-strong bg-surface px-3 py-1.5 font-sans text-xs shadow-sm"
          >
            <a
              href={textFragmentUrl(filing.edgar_url, s.text)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-accent underline"
            >
              Open in SEC filing<span aria-hidden="true"> ↗</span>
              <span className="sr-only"> (opens in a new tab, scrolls to this sentence where supported)</span>
            </a>
            <a href={filing.edgar_url} target="_blank" rel="noopener noreferrer" className="text-ink-muted underline">
              Filing without highlight<span aria-hidden="true"> ↗</span>
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            <span className="text-ink-faint">
              FY{filing.fiscal_year} {filing.form}
              {isFixture ? " · fixture link, not a real filing" : ""}
            </span>
            <button type="button" onClick={onCloseAction} className="ml-auto text-ink-muted hover:text-ink" aria-label="Close sentence actions">
              ✕
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function HiddenRun({ count, unit }: { count: number; unit: string }) {
  return (
    <p className="my-1 ml-[108px] text-xs italic text-ink-faint">
      <span aria-hidden="true">⋯ </span>
      {count} unchanged {unit}
      {count === 1 ? "" : "s"} hidden
    </p>
  );
}

interface DetailProps {
  change: Change;
  index: Record<string, SentenceRef>;
  filings: { old: FilingRef; new: FilingRef };
  isFixture: boolean;
}

export function ChangeDetail({ change, index, filings, isFixture }: DetailProps) {
  const [view, setView] = useState<ViewMode>("split");
  const [showUnchanged, setShowUnchanged] = useState(true);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const isHeading = useCallback((id: string) => index[id]?.is_heading === true, [index]);
  const visibleSentence = useCallback(
    (s: Sentence) => showUnchanged || s.status !== "unchanged" || isHeading(s.id),
    [showUnchanged, isHeading],
  );

  const jumpTo = useCallback(
    (id: string) => {
      const sentence = change.sentences.find((s) => s.id === id);
      if (!sentence) {
        setMissing(id);
        return;
      }
      setMissing(null);
      if (!showUnchanged && sentence.status === "unchanged" && !isHeading(id)) {
        flushSync(() => setShowUnchanged(true));
      }
      flushSync(() => {
        setHighlightId(id);
        setActionId(id);
      });
      const el = document.getElementById(`s-${id}`);
      if (!el) return;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      el.focus({ preventScroll: true });
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setHighlightId(null), 3000);
    },
    [change.sentences, showUnchanged, isHeading],
  );

  const api: CitationApi = useMemo(() => ({ index, filings, isFixture, jumpTo }), [index, filings, isFixture, jumpTo]);

  const sorted = useMemo(
    () =>
      [...change.sentences].sort(
        (a, b) => a.pair_index - b.pair_index || (a.side === b.side ? 0 : a.side === "old" ? -1 : 1),
      ),
    [change.sentences],
  );
  const oldCount = change.sentences.filter((s) => s.side === "old").length;
  const newCount = change.sentences.length - oldCount;
  const fyTag = (side: Sentence["side"]) => `FY${side === "old" ? filings.old.fiscal_year : filings.new.fiscal_year}`;

  const renderSentence = (s: Sentence, withSideTag: boolean) => (
    <SentenceView
      key={s.id}
      s={s}
      heading={isHeading(s.id)}
      sideTag={withSideTag ? fyTag(s.side) : null}
      highlighted={highlightId === s.id}
      actionOpen={actionId === s.id}
      filing={s.side === "old" ? filings.old : filings.new}
      isFixture={isFixture}
      onCloseAction={() => setActionId(null)}
    />
  );

  /** Renders a list, collapsing runs of hidden unchanged items into one note. */
  function withHiddenRuns<T>(items: T[], isVisible: (x: T) => boolean, render: (x: T) => React.ReactNode, unit: string, keyOf: (x: T) => string) {
    const out: React.ReactNode[] = [];
    let hidden = 0;
    let runKey = "";
    for (const it of items) {
      if (isVisible(it)) {
        if (hidden > 0) out.push(<HiddenRun key={`h-${runKey}`} count={hidden} unit={unit} />);
        hidden = 0;
        out.push(render(it));
      } else {
        if (hidden === 0) runKey = keyOf(it);
        hidden += 1;
      }
    }
    if (hidden > 0) out.push(<HiddenRun key={`h-${runKey}`} count={hidden} unit={unit} />);
    return out;
  }

  function renderSplit() {
    const oldFiling = filings.old;
    const newFiling = filings.new;
    const header = (
      <div className={`sticky ${isFixture ? "top-[96px]" : "top-14"} z-10 grid grid-cols-2 gap-6 border-b border-line bg-surface pb-2 pt-1 text-xs font-semibold uppercase tracking-wide text-ink-faint`}>
        <span>
          Older · FY{oldFiling.fiscal_year} {oldFiling.form}
        </span>
        <span>
          Newer · FY{newFiling.fiscal_year} {newFiling.form}
        </span>
      </div>
    );
    if (oldCount === 0 || newCount === 0) {
      const present = sorted;
      const absentSide = oldCount === 0 ? "old" : "new";
      const absentBox = (
        <div className="flex h-full min-h-[120px] items-start rounded border border-dashed border-line-strong bg-[repeating-linear-gradient(135deg,var(--color-paper),var(--color-paper)_8px,var(--color-sunken)_8px,var(--color-sunken)_16px)] p-4 text-sm text-ink-muted">
          <p>
            This risk factor does not appear in the FY{absentSide === "old" ? oldFiling.fiscal_year : newFiling.fiscal_year} filing.
          </p>
        </div>
      );
      const presentCol = <div className="space-y-1">{withHiddenRuns(present, visibleSentence, (s) => renderSentence(s, false), "sentence", (s) => s.id)}</div>;
      return (
        <div>
          {header}
          <div className="mt-2 grid grid-cols-2 gap-6">
            {absentSide === "old" ? absentBox : presentCol}
            {absentSide === "old" ? presentCol : absentBox}
          </div>
        </div>
      );
    }
    const pairs = new Map<number, { old: Sentence[]; new: Sentence[] }>();
    for (const s of sorted) {
      const p = pairs.get(s.pair_index) ?? { old: [], new: [] };
      p[s.side].push(s);
      pairs.set(s.pair_index, p);
    }
    const rows = [...pairs.entries()].sort((a, b) => a[0] - b[0]);
    const rowVisible = ([, p]: [number, { old: Sentence[]; new: Sentence[] }]) => [...p.old, ...p.new].some(visibleSentence);
    const emptyCell = (side: "old" | "new") => (
      <div className="h-full min-h-8 rounded border border-dashed border-line bg-[repeating-linear-gradient(135deg,transparent,transparent_6px,var(--color-sunken)_6px,var(--color-sunken)_12px)]">
        <span className="sr-only">No corresponding sentence in the {side === "old" ? "older" : "newer"} filing.</span>
      </div>
    );
    return (
      <div>
        {header}
        <div className="mt-2 space-y-1">
          {withHiddenRuns(
            rows,
            rowVisible,
            ([pi, p]) => (
              <div key={pi} className="grid grid-cols-2 gap-6">
                <div className="space-y-1">{p.old.length ? p.old.map((s) => renderSentence(s, false)) : emptyCell("old")}</div>
                <div className="space-y-1">{p.new.length ? p.new.map((s) => renderSentence(s, false)) : emptyCell("new")}</div>
              </div>
            ),
            "sentence pair",
            ([pi]) => String(pi),
          )}
        </div>
      </div>
    );
  }

  function renderInline() {
    return (
      <div className="max-w-[880px] space-y-1">
        {withHiddenRuns(sorted, visibleSentence, (s) => renderSentence(s, s.status !== "unchanged" || isHeading(s.id)), "sentence", (s) => s.id)}
      </div>
    );
  }

  const missingRef = missing ? index[missing] : null;

  return (
    <CitationContext.Provider value={api}>
      <div className="grid grid-cols-[minmax(0,1fr)_400px] items-start gap-8">
        <section aria-labelledby="diff-heading" className="min-w-0 rounded-lg border border-line bg-surface p-5">
          <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line pb-4">
            <h2 id="diff-heading" className="text-base font-bold text-ink">
              Sentence diff
            </h2>
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
                  onClick={() => setView(mode)}
                  className={`rounded px-3 py-1 text-sm font-medium ${
                    view === mode ? "bg-ink text-white" : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked={showUnchanged}
                onChange={(e) => setShowUnchanged(e.target.checked)}
                className="h-4 w-4 accent-ink"
              />
              Show unchanged sentences
            </label>
            <ul className="ml-auto flex flex-wrap items-center gap-3 text-xs text-ink-muted" aria-label="Legend">
              <li>
                <span className="font-mono font-bold text-add-fg">+</span> <ins className="span-ins">added</ins>
              </li>
              <li>
                <span className="font-mono font-bold text-del-fg">−</span> <del className="span-del">removed</del>
              </li>
              <li>
                <span className="font-mono font-bold text-mod-fg">~</span> modified
              </li>
              <li className="text-ink-faint">unchanged (muted)</li>
            </ul>
          </div>
          {change.sentences.length === 0 ? (
            <p className="text-ink-muted">No sentences recorded for this change.</p>
          ) : view === "split" ? (
            renderSplit()
          ) : (
            renderInline()
          )}
        </section>

        <aside
          aria-label="Why this change scored as it did"
          className={`sticky ${isFixture ? "top-[108px] max-h-[calc(100vh-124px)]" : "top-[72px] max-h-[calc(100vh-88px)]"} space-y-4 overflow-y-auto pb-2 pr-1`}
        >
          {missing ? (
            <div role="status" className="rounded border border-mod-line bg-mod-bg p-3 text-sm text-mod-fg">
              <p className="font-semibold">That cited sentence is not part of this diff.</p>
              {missingRef ? <p className="mt-1 font-serif text-ink">{missingRef.text}</p> : <p className="font-mono">{missing}</p>}
              <button type="button" className="mt-1 underline" onClick={() => setMissing(null)}>
                Dismiss
              </button>
            </div>
          ) : null}
          <ScoreBreakdownPanel change={change} />
          <AiInterpretationPanel interp={change.interpretation} />
          <SignalsPanel change={change} />
        </aside>
      </div>
    </CitationContext.Provider>
  );
}
