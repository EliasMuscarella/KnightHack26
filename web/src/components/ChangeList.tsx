"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { CategoryChip, ChangeTypeBadge, ScoreBar } from "@/components/ui";
import { categoryLabel, CHANGE_TYPE_ORDER, changeTypeMeta } from "@/lib/format";

export interface ChangeRow {
  id: string;
  rank: number;
  title: string;
  change_type: string;
  categories: string[];
  section_group: string | null;
  score: number;
  added: number;
  removed: number;
  modified: number;
}

type SortKey = "score" | "title";

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function FilterChip({
  pressed,
  onClick,
  children,
  count,
}: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
        pressed
          ? "border-ink bg-ink text-white"
          : "border-line-strong bg-surface text-ink-muted hover:border-ink hover:text-ink"
      }`}
    >
      {pressed ? <span aria-hidden="true">✓</span> : null}
      {children}
      {count !== undefined ? <span className="tabular-nums opacity-80">{count}</span> : null}
    </button>
  );
}

export function ChangeList({
  ticker,
  rows,
  countsByType,
}: {
  ticker: string;
  rows: ChangeRow[];
  countsByType: Record<string, number>;
}) {
  const [types, setTypes] = useState<string[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("score");

  const categoryCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) for (const c of r.categories) m.set(c, (m.get(c) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1] || categoryLabel(a[0]).localeCompare(categoryLabel(b[0])));
  }, [rows]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = rows.filter(
      (r) =>
        (types.length === 0 || types.includes(r.change_type)) &&
        (cats.length === 0 || r.categories.some((c) => cats.includes(c))) &&
        (q === "" || r.title.toLowerCase().includes(q)),
    );
    return filtered.sort((a, b) =>
      sort === "title" ? a.title.localeCompare(b.title) : b.score - a.score || a.rank - b.rank,
    );
  }, [rows, types, cats, query, sort]);

  const filtersActive = types.length > 0 || cats.length > 0 || query.trim() !== "";

  return (
    <section aria-labelledby="changes-heading" className="space-y-5">
      <div>
        <h2 id="changes-heading" className="text-xl font-bold text-ink">
          Changes by type
        </h2>
        <p className="mt-0.5 text-sm text-ink-faint">Select a type to filter the list.</p>
      </div>
      <div className="grid grid-cols-6 gap-3">
        {CHANGE_TYPE_ORDER.map((t) => {
          const meta = changeTypeMeta(t);
          const count = countsByType[t] ?? 0;
          const pressed = types.includes(t);
          return (
            <button
              key={t}
              type="button"
              aria-pressed={pressed}
              onClick={() => setTypes((prev) => toggle(prev, t))}
              disabled={count === 0 && !pressed}
              className={`flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-55 ${
                pressed ? "border-ink bg-surface shadow-[inset_0_0_0_1px_var(--color-ink)]" : "border-line bg-surface hover:border-ink"
              }`}
            >
              <span className="flex w-full items-center justify-between">
                <ChangeTypeBadge type={t} size="sm" />
                {pressed ? (
                  <span className="text-xs font-semibold text-ink">
                    <span aria-hidden="true">✓</span> filtered
                  </span>
                ) : null}
              </span>
              <span className="text-2xl font-bold tabular-nums text-ink">{count}</span>
              <span className="text-xs leading-snug text-ink-faint">{meta.description}</span>
            </button>
          );
        })}
      </div>

      <div className="rounded-lg border border-line bg-surface">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-5 py-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="font-medium text-ink-muted">Filter titles</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. tariffs"
              className="h-8 w-56 rounded border border-line-strong bg-surface px-2 text-sm focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <span className="font-medium text-ink-muted">Sort by</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="h-8 rounded border border-line-strong bg-surface px-2 text-sm focus:border-accent focus:outline-none"
            >
              <option value="score">Change score (high to low)</option>
              <option value="title">Title (A to Z)</option>
            </select>
          </label>
          <p className="ml-auto text-sm text-ink-faint" aria-live="polite">
            Showing <strong className="text-ink">{visible.length}</strong> of {rows.length}
          </p>
          {filtersActive ? (
            <button
              type="button"
              onClick={() => {
                setTypes([]);
                setCats([]);
                setQuery("");
              }}
              className="text-sm font-medium text-accent underline"
            >
              Clear filters
            </button>
          ) : null}
        </div>
        <div className="space-y-2 border-b border-line px-5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-24 text-xs font-semibold uppercase tracking-wide text-ink-faint">Type</span>
            {CHANGE_TYPE_ORDER.filter((t) => (countsByType[t] ?? 0) > 0).map((t) => (
              <FilterChip key={t} pressed={types.includes(t)} onClick={() => setTypes((p) => toggle(p, t))} count={countsByType[t]}>
                <span aria-hidden="true" className="font-mono">
                  {changeTypeMeta(t).marker}
                </span>
                {changeTypeMeta(t).label}
              </FilterChip>
            ))}
          </div>
          {categoryCounts.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-24 text-xs font-semibold uppercase tracking-wide text-ink-faint">Category</span>
              {categoryCounts.map(([c, n]) => (
                <FilterChip key={c} pressed={cats.includes(c)} onClick={() => setCats((p) => toggle(p, c))} count={n}>
                  {categoryLabel(c)}
                </FilterChip>
              ))}
            </div>
          ) : null}
        </div>

        <div
          className="grid grid-cols-[56px_minmax(0,1fr)_170px_150px_150px] gap-4 border-b border-line bg-sunken px-5 py-2 text-xs font-semibold uppercase tracking-wide text-ink-faint"
          aria-hidden="true"
        >
          <span>Rank</span>
          <span>Risk factor</span>
          <span>Change</span>
          <span title="Sentences added / removed / modified">Sentences</span>
          <span>Change score</span>
        </div>
        {visible.length === 0 ? (
          <p className="px-5 py-10 text-center text-ink-muted">No changes match these filters.</p>
        ) : (
          <ol aria-label="Ranked changes">
            {visible.map((r) => (
              <li key={r.id} className="border-b border-line last:border-b-0">
                <Link
                  href={`/c/${encodeURIComponent(ticker)}/${encodeURIComponent(r.id)}`}
                  className="grid grid-cols-[56px_minmax(0,1fr)_170px_150px_150px] items-start gap-4 px-5 py-4 hover:bg-paper focus-visible:bg-paper"
                >
                  <span className="pt-0.5 font-mono text-sm font-semibold tabular-nums text-ink-faint">
                    <span className="sr-only">Rank </span>#{r.rank}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-semibold leading-snug text-ink underline-offset-2 hover:underline">{r.title}</span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {r.categories.map((c) => (
                        <CategoryChip key={c} category={c} />
                      ))}
                      {r.section_group ? (
                        <span className="text-xs text-ink-faint">
                          <span aria-hidden="true">· </span>
                          {r.section_group}
                        </span>
                      ) : null}
                    </span>
                  </span>
                  <span className="pt-0.5">
                    <ChangeTypeBadge type={r.change_type} />
                  </span>
                  <span className="flex gap-3 pt-1 font-mono text-sm tabular-nums">
                    <span className="text-add-fg" title={`${r.added} sentences added`}>
                      +{r.added}
                      <span className="sr-only"> added</span>
                    </span>
                    <span className="text-del-fg" title={`${r.removed} sentences removed`}>
                      −{r.removed}
                      <span className="sr-only"> removed</span>
                    </span>
                    <span className="text-mod-fg" title={`${r.modified} sentences modified`}>
                      ~{r.modified}
                      <span className="sr-only"> modified</span>
                    </span>
                  </span>
                  <span className="pt-1">
                    <ScoreBar score={r.score} />
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
