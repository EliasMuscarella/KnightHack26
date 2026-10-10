import Link from "next/link";

import { HighlightKindBadge } from "@/components/ui";
import { formatDate } from "@/lib/format";
import type { CompanyListing } from "@/lib/types";
import { meaningfulCount } from "@/lib/vocabulary";

export function CompanyCardView({ company }: { company: CompanyListing }) {
  const { meaningful, total: summed } = meaningfulCount(company.by_change_type);
  const total = company.total_changes || summed;
  const top = company.top_highlight;
  return (
    <Link
      href={`/c/${encodeURIComponent(company.ticker)}`}
      className="group flex h-full flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-sm transition hover:border-accent hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-sm font-bold tracking-wide text-accent">{company.ticker}</p>
          <h3 className="mt-0.5 text-lg font-semibold leading-snug text-ink group-hover:underline">{company.name}</h3>
        </div>
        {company.is_fixture ? (
          <span className="shrink-0 rounded border border-fixture-line bg-fixture-bg px-1.5 py-px text-xs font-bold text-fixture-fg">
            FIXTURE
          </span>
        ) : null}
      </div>
      <p className="text-base text-ink">
        <span className="font-semibold tabular-nums">
          {meaningful} meaningful {meaningful === 1 ? "change" : "changes"}
        </span>
        <span className="text-ink-muted">
          {" "}
          · {total} risk {total === 1 ? "factor" : "factors"}
        </span>
      </p>
      <p className="text-sm text-ink-muted">
        FY{company.old_fiscal_year} <span aria-hidden="true">→</span>
        <span className="sr-only">to</span> FY{company.new_fiscal_year}
        {company.old_filing_date || company.new_filing_date ? (
          <>
            {" "}
            · filed {formatDate(company.old_filing_date)} and {formatDate(company.new_filing_date)}
          </>
        ) : null}
      </p>
      {top ? (
        <div className="mt-auto border-t border-line pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Top change</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <HighlightKindBadge kind={top.kind} size="sm" />
            <span className="text-sm font-medium leading-snug text-ink">{top.short_title}</span>
          </div>
        </div>
      ) : null}
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
