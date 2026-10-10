import Link from "next/link";

import { CompanyLogo } from "@/components/CompanyLogo";
import { ChangeBadge } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { displayName } from "@/lib/names";
import type { CompanyListing } from "@/lib/types";
import { displayTitle, meaningfulCount } from "@/lib/vocabulary";

/** "Published by {who}, {date}" / "Published {date}" / nothing. */
function publishedLine(company: CompanyListing): string | null {
  const by = typeof company.published_by === "string" ? company.published_by.trim() : "";
  const date = typeof company.published_at === "string" && company.published_at ? formatDate(company.published_at) : "";
  if (!date) return by ? `Published by ${by}` : null;
  return by ? `Published by ${by}, ${date}` : `Published ${date}`;
}

/** Library cards are the only boxes on the home page. */
export function CompanyCardView({ company }: { company: CompanyListing }) {
  const { meaningful, total: summed } = meaningfulCount(company.by_change_type);
  const total = company.total_changes || summed;
  const top = company.top_highlight;
  const name = displayName(company.name);
  const published = publishedLine(company);
  return (
    <Link
      href={`/c/${encodeURIComponent(company.ticker)}`}
      className="group flex h-full flex-col rounded-lg border border-line bg-surface p-6 transition hover:border-ink hover:shadow-card"
    >
      <div className="flex items-center gap-3">
        <CompanyLogo ticker={company.ticker} name={name} size="sm" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-medium leading-snug text-ink group-hover:underline">{name}</h3>
          <p className="text-sm text-ink-secondary">
            <span className="font-medium text-ink">{company.ticker}</span>, FY{company.old_fiscal_year} and FY{company.new_fiscal_year}
            {company.is_fixture ? ", fixture data" : ""}
          </p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 border-y border-line py-3">
        <div className="pr-4">
          <dt className="text-sm text-ink-secondary">Changed meaningfully</dt>
          <dd className="mt-0.5 text-lg font-medium leading-tight text-ink">{meaningful}</dd>
        </div>
        <div className="border-l border-line pl-4">
          <dt className="text-sm text-ink-secondary">Risk factors compared</dt>
          <dd className="mt-0.5 text-lg font-medium leading-tight text-ink">{total}</dd>
        </div>
      </dl>
      {top ? (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-ink-secondary">Top change</span>
            <ChangeBadge kind={top.kind} size="sm" figureChanged={top.figure_changed === true} detail={top.detail ?? null} />
          </div>
          <p className="mt-1.5 line-clamp-2 text-base leading-snug text-ink" title={top.title || top.short_title}>
            {displayTitle(top.short_title, top.title, company.name)}
          </p>
        </div>
      ) : meaningful === 0 ? (
        <p className="mt-4 text-base text-ink-secondary">No meaningful changes this year.</p>
      ) : null}
      {published ? <p className="mt-auto pt-4 text-sm text-ink-secondary">{published}</p> : null}
    </Link>
  );
}

export function CompanyGrid({ companies }: { companies: CompanyListing[] }) {
  return (
    <ul className="grid gap-4 min-[900px]:grid-cols-3">
      {companies.map((c) => (
        <li key={c.ticker}>
          <CompanyCardView company={c} />
        </li>
      ))}
    </ul>
  );
}
