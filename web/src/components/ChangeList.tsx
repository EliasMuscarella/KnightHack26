"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ChangeBadge, ChangeLevel, SectionTitle } from "@/components/ui";
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

/** Shared by the column header and every row, so the three columns line up like a table. */
const ROW_GRID = "grid grid-cols-[minmax(0,1fr)_170px_220px] items-center gap-6";

/** Visual column labels; the rows carry their own accessible text, so this is hidden from screen readers. */
function ColumnHeader() {
  return (
    <div aria-hidden="true" className={`${ROW_GRID} border-b border-line pb-2 pt-3 text-sm text-ink-secondary`}>
      <span>Risk factor</span>
      <span>Type of change</span>
      <span>{CHANGE_LEVEL.prefix}</span>
    </div>
  );
}

/** "12 sentences added, 3 modified" (the first part carries the noun). */
export function sentenceCountLine(added: number, removed: number, modified: number): string {
  const parts: [number, string][] = [
    [added, "added"],
    [removed, "removed"],
    [modified, "modified"],
  ];
  const nonzero = parts.filter(([n]) => n > 0);
  if (nonzero.length === 0) return "No sentence-level changes";
  return nonzero.map(([n, verb], i) => (i === 0 ? `${n} ${n === 1 ? "sentence" : "sentences"} ${verb}` : `${n} ${verb}`)).join(", ");
}

function FilterButton({ pressed, onClick, children, count, title }: { pressed: boolean; onClick: () => void; children: React.ReactNode; count?: number; title?: string }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1 text-sm transition ${
        pressed ? "border-ink bg-ink text-on-ink" : "border-line bg-surface text-ink-secondary hover:border-ink hover:text-ink"
      }`}
    >
      {children}
      {count !== undefined ? <span>{count}</span> : null}
    </button>
  );
}

function Row({ ticker, r }: { ticker: string; r: ChangeRow }) {
  return (
    <li className="border-b border-line last:border-b-0">
      <Link
        href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(r.id)}`}
        className={`${ROW_GRID} -mx-3 px-3 py-3 hover:bg-surface focus-visible:bg-surface`}
      >
        <span className="min-w-0">
          <span className="line-clamp-2 text-base font-medium leading-snug text-ink underline-offset-2 hover:underline" title={r.title}>
            {displayTitle(r.short_title, r.title)}
          </span>
          <span className="mt-0.5 block text-sm text-ink-secondary">
            {sentenceCountLine(r.added, r.removed, r.modified)}
            {r.categories.length > 0 ? <span className="sr-only">. Topics: {r.categories.map(categoryLabel).join(", ")}</span> : null}
          </span>
        </span>
        <span>
          <ChangeBadge type={r.change_type} size="sm" />
        </span>
        <span>
          <ChangeLevel score={r.score} changeType={r.change_type} size="sm" />
        </span>
      </Link>
    </li>
  );
}

export function ChangeList({ ticker, rows, initialTopic = "" }: { ticker: string; rows: ChangeRow[]; initialTopic?: string }) {
  const [type, setType] = useState<string | null>(null);
  const [topic, setTopic] = useState<string>(() => (rows.some((r) => r.categories.includes(initialTopic)) ? initialTopic : ""));
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
  const collapseUnchanged = type === null;
  const changed = collapseUnchanged ? filtered.filter((r) => r.change_type !== UNCHANGED) : filtered;
  const unchanged = collapseUnchanged ? filtered.filter((r) => r.change_type === UNCHANGED) : [];

  return (
    <section aria-labelledby="changes-heading" className="space-y-4">
      <SectionTitle id="changes-heading" aside={<span title={CHANGE_LEVEL.helper}>{CHANGE_LEVEL.tableNote}</span>}>
        All changes
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <div role="group" aria-label="Filter by type of change" className="flex flex-wrap items-center gap-2">
          <FilterButton pressed={type === null} onClick={() => setType(null)} count={rows.length}>
            All
          </FilterButton>
          {CHANGE_TYPE_ORDER.filter((t) => (typeCounts.get(t) ?? 0) > 0).map((t) => {
            const v = changeTypeVocab(t);
            return (
              <FilterButton key={t} pressed={type === t} onClick={() => setType((prev) => (prev === t ? null : t))} count={typeCounts.get(t)} title={v.helper}>
                {v.label}
              </FilterButton>
            );
          })}
        </div>
        {topics.length > 0 ? (
          <label className="ml-auto flex items-center gap-2 text-sm text-ink-secondary">
            Topic
            <select
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="h-8 rounded-md border border-line-input bg-surface px-2 text-sm text-ink focus:border-accent focus:outline-none"
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
        <p className="py-10 text-center text-ink-secondary">No risk factors match these filters.</p>
      ) : (
        <div className="border-t border-line">
          <ColumnHeader />
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
                className="flex w-full items-center gap-2 py-3 text-left text-sm font-medium text-accent hover:underline"
              >
                <span aria-hidden="true" className={`transition ${showUnchanged ? "rotate-90" : ""}`}>
                  ▸
                </span>
                {showUnchanged ? "Hide" : "Show"} {unchanged.length} essentially unchanged risk {unchanged.length === 1 ? "factor" : "factors"}
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
        </div>
      )}
    </section>
  );
}
