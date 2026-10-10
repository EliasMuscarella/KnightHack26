"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";

import type { Change, Sentence } from "@/types/comparison";

import { AiInterpretationPanel, ScoreBreakdownPanel, SignalsPanel } from "@/components/ChangePanels";
import { CitationContext, type CitationApi, type FilingRef, type SentenceRef } from "@/components/citations";
import { FilingLink } from "@/components/ui";
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

/** Splits a span into leading whitespace, the marked core, and trailing whitespace. */
function splitWhitespace(text: string): [string, string, string] {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
  return m ? [m[1], m[2], m[3]] : ["", text, ""];
}

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
  sideTag: string | null;
  highlighted: boolean;
  actionOpen: boolean;
  filing: FilingRef;
  isFixture: boolean;
  onCloseAction: () => void;
  onBack: (() => void) | null;
  /** Inline view: id of an identical unchanged old-side sentence shown merged into this one. */
  aliasId?: string;
  /**
   * "stacked" (side by side): status tag on a label line above the text, so the text gets
   * the full column width. "gutter" (inline): status tag in a narrow left gutter.
   */
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

const STATUS_TINT: Record<Sentence["status"], string> = {
  added: "bg-add-bg/40",
  removed: "bg-del-bg/40",
  modified: "",
  unchanged: "",
};

function StatusTag({ s, highlighted, sideTag, stacked }: { s: Sentence; highlighted: boolean; sideTag: string | null; stacked: boolean }) {
  const meta = STATUS_META[s.status];
  return (
    <>
      {highlighted ? (
        <span className={`${stacked ? "" : "mb-0.5 block "}font-bold text-ink`}>
          <span aria-hidden="true">▶ </span>Cited
        </span>
      ) : null}
      {s.status !== "unchanged" ? (
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="font-mono text-sm leading-none">
            {meta.marker}
          </span>
          {meta.label}
        </span>
      ) : (
        <span className="sr-only">Unchanged</span>
      )}
      {sideTag ? <span className={`${stacked ? "" : "mt-0.5 block "}font-mono font-medium text-ink-faint`}>{sideTag}</span> : null}
    </>
  );
}

function SentenceInner({ s, heading, sideTag, highlighted, actionOpen, filing, isFixture, onCloseAction, onBack, layout }: SentenceViewProps) {
  const meta = STATUS_META[s.status];
  const stacked = layout === "stacked";
  const showLabelLine = highlighted || s.status !== "unchanged" || !!sideTag;
  const actions = actionOpen ? (
    <div
      role="group"
      aria-label="Cited sentence actions"
      className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-line-strong bg-surface px-3 py-1.5 font-sans text-xs shadow-sm"
    >
      <FilingLink href={textFragmentUrl(filing.edgar_url, s.text)} isFixture={isFixture} className="font-semibold">
        Open in SEC filing
      </FilingLink>
      <FilingLink href={filing.edgar_url} isFixture={isFixture}>
        Filing without highlight
      </FilingLink>
      <span className="text-ink-faint">
        FY{filing.fiscal_year} {filing.form}
      </span>
      {onBack ? (
        <button type="button" onClick={onBack} className="ml-auto font-semibold text-accent underline">
          <span aria-hidden="true">↩ </span>Back to citation
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
  const boxClass = `cite-target rounded-r border-l-4 outline-none ${highlighted ? "cite-flash border-ink" : `${meta.border} ${STATUS_TINT[s.status]}`}`;

  if (stacked) {
    return (
      <div id={`s-${s.id}`} data-sentence-id={s.id} data-status={s.status} tabIndex={-1} className={`${boxClass} py-1.5 pl-3 pr-2`}>
        {showLabelLine ? (
          <p className={`mb-0.5 flex flex-wrap items-center gap-x-2.5 font-sans text-xs font-semibold leading-tight ${meta.gutter}`}>
            <StatusTag s={s} highlighted={highlighted} sideTag={sideTag} stacked />
          </p>
        ) : (
          <span className="sr-only">Unchanged</span>
        )}
        <SentenceBody s={s} heading={heading} />
        {actions}
      </div>
    );
  }
  return (
    <div
      id={`s-${s.id}`}
      data-sentence-id={s.id}
      data-status={s.status}
      tabIndex={-1}
      className={`${boxClass} grid grid-cols-[72px_minmax(0,1fr)] gap-2.5 py-1.5 pl-2 pr-3`}
    >
      <div className={`pt-1 font-sans text-xs font-semibold leading-tight ${meta.gutter}`}>
        <StatusTag s={s} highlighted={highlighted} sideTag={sideTag} stacked={false} />
      </div>
      <div className="min-w-0">
        <SentenceBody s={s} heading={heading} />
        {actions}
      </div>
    </div>
  );
}

function HiddenRun({ count, unit, indent }: { count: number; unit: string; indent: string }) {
  return (
    <p className={`my-1 ${indent} font-sans text-xs italic text-ink-faint`}>
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
  const [returnEl, setReturnEl] = useState<HTMLElement | null>(null);
  const [asideFits, setAsideFits] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const asideRef = useRef<HTMLElement | null>(null);
  const stickyTop = isFixture ? 112 : 72;

  // The panel column is sticky only when it fits in the viewport; otherwise it scrolls with
  // the page so nothing (e.g. the AI section) is hidden behind an inner scroll area.
  useEffect(() => {
    const el = asideRef.current;
    if (!el) return;
    const check = () => setAsideFits(el.offsetHeight <= window.innerHeight - stickyTop - 16);
    const ro = new ResizeObserver(check);
    ro.observe(el);
    window.addEventListener("resize", check);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", check);
    };
  }, [stickyTop]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const isHeading = useCallback((id: string) => index[id]?.is_heading === true, [index]);
  const visibleSentence = useCallback(
    (s: Sentence) => showUnchanged || s.status !== "unchanged" || isHeading(s.id),
    [showUnchanged, isHeading],
  );

  const jumpTo = useCallback(
    (id: string, source?: HTMLElement | null) => {
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

  const renderSentence = (s: Sentence, withSideTag: boolean, aliasId?: string) => (
    <SentenceView
      key={s.id}
      s={s}
      layout={view === "split" ? "stacked" : "gutter"}
      aliasId={aliasId}
      heading={isHeading(s.id)}
      sideTag={aliasId ? "both years" : withSideTag ? fyTag(s.side) : null}
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

  /** Renders a list, collapsing runs of hidden unchanged items into one note. */
  const hiddenIndent = view === "split" ? "ml-4" : "ml-[86px]";
  function withHiddenRuns<T>(items: T[], isVisible: (x: T) => boolean, render: (x: T) => React.ReactNode, unit: string, keyOf: (x: T) => string) {
    const out: React.ReactNode[] = [];
    let hidden = 0;
    let runKey = "";
    for (const it of items) {
      if (isVisible(it)) {
        if (hidden > 0) out.push(<HiddenRun key={`h-${runKey}`} count={hidden} unit={unit} indent={hiddenIndent} />);
        hidden = 0;
        out.push(render(it));
      } else {
        if (hidden === 0) runKey = keyOf(it);
        hidden += 1;
      }
    }
    if (hidden > 0) out.push(<HiddenRun key={`h-${runKey}`} count={hidden} unit={unit} indent={hiddenIndent} />);
    return out;
  }

  function renderSplit() {
    const oldFiling = filings.old;
    const newFiling = filings.new;
    const header = (
      <div className={`sticky ${isFixture ? "top-[100px]" : "top-14"} z-10 grid grid-cols-2 gap-5 border-b border-line bg-surface pb-2 pt-1 text-xs font-semibold uppercase tracking-wide text-ink-faint`}>
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
        <div className="split-view">
          {header}
          <div className="mt-2 grid grid-cols-2 gap-5">
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
      <div className="split-view">
        {header}
        <div className="mt-2 space-y-1">
          {withHiddenRuns(
            rows,
            rowVisible,
            ([pi, p]) => (
              <div key={pi} className="grid grid-cols-2 gap-5">
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
    // Unified view: an unchanged pair whose two sentences are byte-identical is shown once
    // (like a context line in a unified diff); the old id stays addressable for citations.
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
    const items = sorted.filter((s) => !merged.has(s.id));
    return (
      // Line-length cap for the unified view: ~75 characters of filing text per line. A literal
      // 75ch is wider (ch is the width of "0"; prose averages ~0.42em per character), so the
      // text column is 34rem (32em of the 17px filing text) plus the 106px gutter + padding.
      <div className="max-w-[calc(34rem+106px)] space-y-1">
        {withHiddenRuns(
          items,
          visibleSentence,
          (s) => renderSentence(s, true, identicalOld(s)?.id),
          "sentence",
          (s) => s.id,
        )}
      </div>
    );
  }

  const missingRef = missing ? index[missing] : null;

  return (
    <CitationContext.Provider value={api}>
      <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-5">
        <section aria-labelledby="diff-heading" className="min-w-0 rounded-lg border border-line bg-surface p-4">
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
          ref={asideRef}
          aria-label="Why this change scored as it did"
          style={asideFits ? { position: "sticky", top: stickyTop } : undefined}
          className="space-y-4"
        >
          {missing ? (
            <div role="status" className="rounded border border-mod-line bg-mod-bg p-3 text-sm text-mod-fg">
              <p className="font-semibold">That cited sentence is not part of this diff.</p>
              {missingRef ? <p className="mt-1 font-serif text-ink">{missingRef.text}</p> : <p className="font-mono">{missing}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                {missingRef ? (
                  <FilingLink
                    href={textFragmentUrl(filings[missingRef.side].edgar_url, missingRef.text)}
                    isFixture={isFixture}
                    className="font-semibold"
                  >
                    Open in SEC filing (FY{filings[missingRef.side].fiscal_year})
                  </FilingLink>
                ) : null}
                <button type="button" className="underline" onClick={() => setMissing(null)}>
                  Dismiss
                </button>
              </div>
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
