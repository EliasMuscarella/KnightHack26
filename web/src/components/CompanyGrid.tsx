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
        <div className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
          <h3 className="text-lg font-medium leading-snug text-ink group-hover:underline">{name}</h3>
          <span className="text-sm text-ink-secondary">{company.ticker}</span>
        </div>
      </div>
      <p className="mt-1 text-sm text-ink-secondary">
        FY{company.old_fiscal_year} and FY{company.new_fiscal_year} annual reports
        {company.is_fixture ? ", fixture data" : ""}
      </p>
      <p className="mt-5">
        {meaningful > 0 ? (
          <>
            <span className="text-xl font-medium leading-none text-ink">{meaningful}</span>
            <span className="ml-2 text-sm text-ink-secondary">
              meaningful {meaningful === 1 ? "change" : "changes"} out of {total} risk factors
            </span>
          </>
        ) : (
          <span className="text-base text-ink">No meaningful changes this year, across {total} risk factors</span>
        )}
      </p>
      {top ? (
        <div className="mt-5 border-t border-line pt-4">
          <p className="text-sm text-ink-secondary">Top change</p>
          <div className="mt-1.5">
            <ChangeBadge kind={top.kind} size="sm" figureChanged={top.figure_changed === true} />
          </div>
          <p className="mt-1.5 line-clamp-2 text-base leading-snug text-ink" title={top.title || top.short_title}>
            {displayTitle(top.short_title, top.title)}
          </p>
        </div>
      ) : null}
      {published ? <p className="mt-auto pt-4 text-sm text-ink-secondary">{published}</p> : null}
    </Link>
  );
}

export function CompanyGrid({ companies }: { companies: CompanyListing[] }) {
  return (
    <ul className="grid gap-5 min-[900px]:grid-cols-3">
      {companies.map((c) => (
        <li key={c.ticker}>
          <CompanyCardView company={c} />
        </li>
      ))}
    </ul>
  );
}
