/**
 * Cross-company trends from the shared report library (server component, no chart library).
 * Every number counts disclosure wording changes; nothing here describes a company's risk.
 */
import Link from "next/link";

import { EmptyState, PageContainer } from "@/components/ui";
import { categoryLabel } from "@/lib/format";
import type { TrendsPayload } from "@/lib/types";
import { FIGURE_NEW_OR_CHANGED, HIGHLIGHT_KIND_VOCAB, changeTypeVocab, highlightKindVocab } from "@/lib/vocabulary";

/** Always-shown columns, then columns shown only when some row has a non-zero value. */
const CORE_CHANGE_TYPES = ["new", "expanded", "materially_reworded"] as const;
const OPTIONAL_CHANGE_TYPES = ["reduced", "removed"] as const;

const KIND_ORDER = Object.keys(HIGHLIGHT_KIND_VOCAB);

/** Aggregated `new_figure` counts mix new and changed figures, so the column says so. */
function kindLabel(kind: string): { label: string; helper: string } {
  if (kind === "new_figure") return FIGURE_NEW_OR_CHANGED;
  const v = highlightKindVocab(kind);
  return { label: v.label, helper: v.helper };
}

function Count({ n }: { n: number }) {
  if (n <= 0) {
    return (
      <>
        <span aria-hidden="true" className="text-ink-faint">
          –
        </span>
        <span className="sr-only">0</span>
      </>
    );
  }
  return <>{n}</>;
}

function Section({ id, title, lead, children }: { id: string; title: string; lead: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-4">
      <div>
        <h2 id={id} className="text-2xl font-bold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-1 max-w-[80ch] text-ink-muted">{lead}</p>
      </div>
      {children}
    </section>
  );
}

function CategoryTable({ rows }: { rows: TrendsPayload["by_category"] }) {
  const counts = new Map<string, Map<string, number>>();
  for (const r of rows) {
    const byType = counts.get(r.category) ?? new Map<string, number>();
    byType.set(r.change_type, (byType.get(r.change_type) ?? 0) + r.companies);
    counts.set(r.category, byType);
  }
  const columns: string[] = [
    ...CORE_CHANGE_TYPES,
    ...OPTIONAL_CHANGE_TYPES.filter((t) => [...counts.values()].some((m) => (m.get(t) ?? 0) > 0)),
  ];
  const body = [...counts.entries()]
    .map(([category, m]) => ({
      category,
      label: categoryLabel(category),
      cells: columns.map((t) => m.get(t) ?? 0),
    }))
    .filter((r) => r.cells.some((n) => n > 0))
    .sort((a, b) => b.cells.reduce((s, n) => s + n, 0) - a.cells.reduce((s, n) => s + n, 0) || a.label.localeCompare(b.label));

  if (body.length === 0) {
    return <p className="text-ink-muted">No category has a changed risk factor in the library yet.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-left text-base">
        <caption className="sr-only">Companies with at least one change of each type, by risk category</caption>
        <thead className="bg-sunken text-xs uppercase tracking-wide text-ink-faint">
          <tr>
            <th scope="col" className="px-4 py-2.5">
              Category
            </th>
            {columns.map((t) => (
              <th key={t} scope="col" className="w-[150px] px-4 py-2.5 text-right" title={changeTypeVocab(t).helper}>
                {changeTypeVocab(t).label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r) => (
            <tr key={r.category} className="border-t border-line">
              <th scope="row" className="px-4 py-2.5 font-medium text-ink">
                {r.label}
              </th>
              {r.cells.map((n, i) => (
                <td key={columns[i]} className="px-4 py-2.5 text-right font-semibold tabular-nums text-ink">
                  <Count n={n} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KindTable({ rows }: { rows: TrendsPayload["by_kind"] }) {
  const companies = new Map<string, { name: string; counts: Map<string, number> }>();
  const kinds = new Set<string>();
  for (const r of rows) {
    const entry = companies.get(r.ticker) ?? { name: r.company_name, counts: new Map<string, number>() };
    entry.counts.set(r.kind, (entry.counts.get(r.kind) ?? 0) + r.highlights);
    companies.set(r.ticker, entry);
    if (r.highlights > 0) kinds.add(r.kind);
  }
  const columns = [...kinds].sort((a, b) => {
    const ia = KIND_ORDER.indexOf(a);
    const ib = KIND_ORDER.indexOf(b);
    return (ia === -1 ? KIND_ORDER.length : ia) - (ib === -1 ? KIND_ORDER.length : ib) || a.localeCompare(b);
  });
  const body = [...companies.entries()].sort(([a], [b]) => a.localeCompare(b));
  const max = Math.max(1, ...body.flatMap(([, c]) => columns.map((k) => c.counts.get(k) ?? 0)));

  if (columns.length === 0 || body.length === 0) {
    return <p className="text-ink-muted">No highlighted changes in the library yet.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full table-fixed text-left text-base">
        <caption className="sr-only">Highlighted changes of each kind, by company</caption>
        <colgroup>
          <col className="w-[30%]" />
          {columns.map((k) => (
            <col key={k} />
          ))}
        </colgroup>
        <thead className="bg-sunken text-xs uppercase tracking-wide text-ink-faint">
          <tr>
            <th scope="col" className="px-4 py-2.5">
              Company
            </th>
            {columns.map((k) => (
              <th key={k} scope="col" className="px-3 py-2.5 align-bottom" title={kindLabel(k).helper}>
                {kindLabel(k).label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map(([ticker, c]) => (
            <tr key={ticker} className="border-t border-line">
              <th scope="row" className="px-4 py-2.5 font-normal">
                <Link href={`/c/${encodeURIComponent(ticker)}`} className="group block min-w-0">
                  <span className="font-mono text-sm font-bold tracking-wide text-accent">{ticker}</span>{" "}
                  <span className="text-ink group-hover:underline">{c.name}</span>
                </Link>
              </th>
              {columns.map((k) => {
                const n = c.counts.get(k) ?? 0;
                return (
                  <td key={k} className="px-3 py-2">
                    <div className="relative h-8 overflow-hidden rounded bg-sunken/60">
                      {n > 0 ? (
                        <div
                          aria-hidden="true"
                          className="absolute inset-y-0 left-0 bg-accent/20"
                          style={{ width: `${Math.round((n / max) * 100)}%` }}
                        />
                      ) : null}
                      <span className="relative flex h-full items-center px-2.5 font-semibold tabular-nums text-ink">
                        <Count n={n} />
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TrendsView({ trends }: { trends: TrendsPayload | null }) {
  const header = <h1 className="text-4xl font-bold tracking-tight text-ink">Trends across the library</h1>;

  if (!trends || !trends.available) {
    return (
      <PageContainer className="space-y-8 py-10">
        {header}
        <EmptyState title="The shared library is not connected on this computer, so cross-company trends are not available." />
      </PageContainer>
    );
  }

  if (trends.companies < 2) {
    return (
      <PageContainer className="space-y-8 py-10">
        {header}
        <EmptyState
          title={`Trends need at least two companies in the shared library. ${trends.companies} is published so far.`}
        >
          <p>
            <Link href="/" className="underline hover:text-ink">
              Back to the report library
            </Link>
          </p>
        </EmptyState>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="space-y-12 py-10">
      <header className="max-w-[80ch]">
        {header}
        <p className="mt-3 text-lg leading-relaxed text-ink-muted">
          Across {trends.companies} companies in the library. These counts describe disclosure wording only, not how risky
          any company is.
        </p>
      </header>
      <Section
        id="where-wording-moved"
        title="Where the wording moved"
        lead="Each number is how many companies have at least one risk factor in that category with that kind of change."
      >
        <CategoryTable rows={trends.by_category} />
      </Section>
      <Section
        id="kinds-of-changes"
        title="What kind of changes companies made"
        lead="Each number is how many highlighted changes of that kind a company's latest report contains. Bars are scaled to the largest number in the table."
      >
        <KindTable rows={trends.by_kind} />
      </Section>
    </PageContainer>
  );
}
