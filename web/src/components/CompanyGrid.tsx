import Link from "next/link";

import { CHANGE_TYPE_ORDER, changeTypeMeta, formatDate } from "@/lib/format";
import type { CompanyListing } from "@/lib/types";

function TypeCounts({ counts }: { counts: Record<string, number> }) {
  const entries = CHANGE_TYPE_ORDER.filter((t) => (counts[t] ?? 0) > 0);
  if (entries.length === 0) return <p className="text-sm text-ink-faint">No changes recorded.</p>;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Changes by type">
      {entries.map((t) => {
        const meta = changeTypeMeta(t);
        return (
          <li
            key={t}
            className={`inline-flex items-center gap-1 rounded border px-1.5 py-px text-xs font-semibold ${meta.badgeClass}`}
          >
            <span aria-hidden="true" className="font-mono">
              {meta.marker}
            </span>
            <span className="tabular-nums">{counts[t]}</span>
            <span className="font-medium">{meta.label}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function CompanyCardView({ company }: { company: CompanyListing }) {
  return (
    <Link
      href={`/c/${encodeURIComponent(company.ticker)}`}
      className="group flex h-full flex-col gap-4 rounded-lg border border-line bg-surface p-5 shadow-sm transition hover:border-accent hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-sm font-bold tracking-wide text-accent">{company.ticker}</p>
          <h3 className="mt-0.5 text-base font-semibold leading-snug text-ink group-hover:underline">
            {company.name}
          </h3>
        </div>
        {company.is_fixture ? (
          <span className="shrink-0 rounded border border-fixture-line bg-fixture-bg px-1.5 py-px text-xs font-bold text-fixture-fg">
            FIXTURE
          </span>
        ) : null}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-ink-faint">Compared</dt>
        <dd className="font-medium text-ink">
          FY{company.old_fiscal_year} <span aria-hidden="true">→</span>
          <span className="sr-only">to</span> FY{company.new_fiscal_year}
        </dd>
        {company.old_filing_date || company.new_filing_date ? (
          <>
            <dt className="text-ink-faint">Filed</dt>
            <dd className="text-ink-muted">
              {formatDate(company.old_filing_date)} <span aria-hidden="true">→</span>
              <span className="sr-only">and</span> {formatDate(company.new_filing_date)}
            </dd>
          </>
        ) : null}
        <dt className="text-ink-faint">Changes</dt>
        <dd className="font-semibold tabular-nums text-ink">{company.total_changes} risk factors</dd>
      </dl>
      <div className="mt-auto">
        <TypeCounts counts={company.by_change_type} />
      </div>
    </Link>
  );
}

export function CompanyGrid({ companies }: { companies: CompanyListing[] }) {
  return (
    <ul className="grid grid-cols-3 gap-5">
      {companies.map((c) => (
        <li key={c.ticker}>
          <CompanyCardView company={c} />
        </li>
      ))}
    </ul>
  );
}
