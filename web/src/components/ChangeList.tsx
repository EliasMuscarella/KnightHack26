"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ChangeLevelTag, ChangeTypeBadge } from "@/components/ui";
import { categoryLabel } from "@/lib/format";
import { CHANGE_LEVEL, CHANGE_TYPE_ORDER, changeTypeVocab, displayTitle } from "@/lib/vocabulary";

export interface ChangeRow {
  id: string;
  rank: number;
  short_title: string;
  title: string;
  change_type: string;
  categories: string[];
  score: number;
  added: number;
  removed: number;
  modified: number;
}

const UNCHANGED = "largely_unchanged";

/** "12 sentences added · 3 modified" (the first part carries the noun). */
export function sentenceCountLine(added: number, removed: number, modified: number): string {
  const parts: [number, string][] = [
    [added, "added"],
    [removed, "removed"],
    [modified, "modified"],
  ];
  const nonzero = parts.filter(([n]) => n > 0);
  if (nonzero.length === 0) return "No sentence-level changes";
  return nonzero
    .map(([n, verb], i) => (i === 0 ? `${n} ${n === 1 ? "sentence" : "sentences"} ${verb}` : `${n} ${verb}`))
    .join(" · ");
}

function TypeFilterButton({
  pressed,
  onClick,
  children,
  count,
  title,
}: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
  count?: number;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition ${
        pressed
          ? "border-ink bg-ink text-white"
          : "border-line-strong bg-surface text-ink-muted hover:border-ink hover:text-ink"
      }`}
    >
      {children}
      {count !== undefined ? <span className="tabular-nums opacity-80">{count}</span> : null}
    </button>
  );
}

function Row({ ticker, r }: { ticker: string; r: ChangeRow }) {
  return (
    <li className="border-b border-line last:border-b-0">
      <Link
        href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(r.id)}`}
        className="grid grid-cols-[minmax(0,1fr)_190px_224px] items-center gap-4 px-5 py-3.5 hover:bg-paper focus-visible:bg-paper"
      >
        <span className="min-w-0">
          <span className="line-clamp-2 font-semibold leading-snug text-ink underline-offset-2 hover:underline" title={r.title}>
            {displayTitle(r.short_title, r.title)}
          </span>
          <span className="mt-0.5 block text-sm text-ink-muted">
            {sentenceCountLine(r.added, r.removed, r.modified)}
            {r.categories.length > 0 ? (
              <span className="text-ink-faint">
                <span aria-hidden="true"> · </span>
                <span className="sr-only">. Topics: </span>
                {r.categories.map(categoryLabel).join(", ")}
              </span>
            ) : null}
          </span>
        </span>
        <span>
          <ChangeTypeBadge type={r.change_type} />
        </span>
        <span>
          <ChangeLevelTag score={r.score} />
        </span>
      </Link>
    </li>
  );
}

export function ChangeList({ ticker, rows }: { ticker: string; rows: ChangeRow[] }) {
  const [type, setType] = useState<string | null>(null);
  const [topic, setTopic] = useState<string>("");
  const [showUnchanged, setShowUnchanged] = useState(false);

  const typeCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.change_type, (m.get(r.change_type) ?? 0) + 1);
    return m;
  }, [rows]);

  const topics = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) for (const c of r.categories) m.set(c, (m.get(c) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1] || categoryLabel(a[0]).localeCompare(categoryLabel(b[0])));
  }, [rows]);

  const filtered = useMemo(
    () =>
      rows
        .filter((r) => (type === null || r.change_type === type) && (topic === "" || r.categories.includes(topic)))
        .sort((a, b) => b.score - a.score || a.rank - b.rank),
    [rows, type, topic],
  );
  // Without a type filter, "Essentially unchanged" rows sit behind a button.
  const collapseUnchanged = type === null;
  const changed = collapseUnchanged ? filtered.filter((r) => r.change_type !== UNCHANGED) : filtered;
  const unchanged = collapseUnchanged ? filtered.filter((r) => r.change_type === UNCHANGED) : [];

  return (
    <section aria-labelledby="changes-heading" className="space-y-3">
      <h2 id="changes-heading" className="text-xl font-bold text-ink">
        All changes
      </h2>
      <div className="rounded-lg border border-line bg-surface">
        <p className="border-b border-line bg-paper px-5 py-2 text-sm text-ink-muted">
          <span aria-hidden="true">ⓘ </span>
          {CHANGE_LEVEL.tableNote}
        </p>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line px-5 py-3">
          <div role="group" aria-label="Filter by type of change" className="flex flex-wrap items-center gap-2">
            <TypeFilterButton pressed={type === null} onClick={() => setType(null)} count={rows.length}>
              All
            </TypeFilterButton>
            {CHANGE_TYPE_ORDER.filter((t) => (typeCounts.get(t) ?? 0) > 0).map((t) => {
              const v = changeTypeVocab(t);
              return (
                <TypeFilterButton
                  key={t}
                  pressed={type === t}
                  onClick={() => setType((prev) => (prev === t ? null : t))}
                  count={typeCounts.get(t)}
                  title={v.helper}
                >
                  {v.marker ? (
                    <span aria-hidden="true" className="font-mono">
                      {v.marker}
                    </span>
                  ) : null}
                  {v.label}
                </TypeFilterButton>
              );
            })}
          </div>
          {topics.length > 0 ? (
            <label className="ml-auto flex items-center gap-2 text-sm">
              <span className="text-ink-faint">Topic</span>
              <select
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="h-8 rounded border border-line-input bg-surface px-2 text-sm text-ink focus:border-accent focus:outline-none"
              >
                <option value="">All topics</option>
                {topics.map(([c, n]) => (
                  <option key={c} value={c}>
                    {categoryLabel(c)} ({n})
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        <p className="sr-only" aria-live="polite">
          Showing {filtered.length} of {rows.length} risk factors.
        </p>
        {filtered.length === 0 ? (
          <p className="px-5 py-10 text-center text-ink-muted">No risk factors match these filters.</p>
        ) : (
          <>
            {changed.length > 0 ? (
              <ol aria-label="Changed risk factors, largest change first">
                {changed.map((r) => (
                  <Row key={r.id} ticker={ticker} r={r} />
                ))}
              </ol>
            ) : null}
            {unchanged.length > 0 ? (
              <div className={changed.length > 0 ? "border-t border-line" : ""}>
                <button
                  type="button"
                  aria-expanded={showUnchanged}
                  onClick={() => setShowUnchanged((v) => !v)}
                  className="flex w-full items-center gap-2 px-5 py-3 text-left text-sm font-semibold text-accent hover:bg-paper"
                >
                  <span aria-hidden="true" className={`font-mono transition ${showUnchanged ? "rotate-90" : ""}`}>
                    ▸
                  </span>
                  {showUnchanged ? "Hide" : "Show"} {unchanged.length} essentially unchanged risk{" "}
                  {unchanged.length === 1 ? "factor" : "factors"}
                </button>
                {showUnchanged ? (
                  <ol aria-label="Essentially unchanged risk factors" className="border-t border-line">
                    {unchanged.map((r) => (
                      <Row key={r.id} ticker={ticker} r={r} />
                    ))}
                  </ol>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
