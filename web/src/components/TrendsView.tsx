"use client";

/**
 * Trends across the report library. Every number here counts disclosure wording; nothing
 * describes a company's risk. Data comes validated from /trends (lib/api.ts). While the shared
 * store is still connecting, the page shows a skeleton and retries quietly; "not connected" is
 * shown only when the store is disabled or offline and nothing local is available.
 */
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ChangeBadge, EmptyState, FilingLink, PageContainer, SectionTitle, Skeleton } from "@/components/ui";
import { parseTrends } from "@/lib/api";
import { categoryLabel, textFragmentUrl } from "@/lib/format";
import { displayName } from "@/lib/names";
import { trimQuote } from "@/lib/quote";
import { buildHeatmap, cellDescription, cellIntensity, cellTone, headlineTopic, type HeatCell, MIX_TYPES, mixTotal, OTHER_CATEGORY, rankTopics, sourceLine, TOP_TOPICS } from "@/lib/trends";
import type { TrendsActual, TrendsCompany, TrendsPayload, TrendsTopic, TrendsTopicExample } from "@/lib/types";

const SOURCE_TAG: Record<TrendsTopic["source"], string | null> = { lexicon: null, entity: "a name", phrase: "a phrase" };
import { CHANGE_TONE, changeTypeVocab, countedLabel, displayTitle } from "@/lib/vocabulary";

const RETRY_MS = 2500;
const RETRY_FOR_MS = 60_000;

// ---------------------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------------------

/** A verbatim sentence with the highlighter (or the strike) over the character ranges the diff marked. */
function SpanMarked({ text, spans, limit, mode = "hl" }: { text: string; spans: [number, number][]; limit?: number; mode?: "hl" | "strike" }) {
  const shown = limit !== undefined && limit < text.length ? text.slice(0, limit) : text;
  const parts: { t: string; hl: boolean }[] = [];
  let pos = 0;
  for (const [a, b] of spans) {
    const start = Math.min(Math.max(a, pos), shown.length);
    const end = Math.min(b, shown.length);
    if (start > pos) parts.push({ t: shown.slice(pos, start), hl: false });
    if (end > start) parts.push({ t: shown.slice(start, end), hl: true });
    pos = Math.max(pos, end);
  }
  if (pos < shown.length) parts.push({ t: shown.slice(pos), hl: false });
  return (
    <>
      {parts.map((p, i) =>
        p.hl ? (
          mode === "hl" ? (
            <mark key={i} className="hl">
              <span className="sr-only">new: </span>
              {p.t}
            </mark>
          ) : (
            <del key={i} className="strike">
              <span className="sr-only">removed: </span>
              {p.t}
            </del>
          )
        ) : (
          <span key={i}>{p.t}</span>
        ),
      )}
    </>
  );
}

function edgarUrl(c: TrendsCompany | undefined, side: "old" | "new"): string | null {
  if (!c) return null;
  const direct = side === "new" ? c.edgar_url_new : c.edgar_url_old;
  if (direct && /^https:\/\/www\.sec\.gov\//.test(direct)) return direct;
  const acc = side === "new" ? c.new_accession : c.old_accession;
  if (c.cik && acc && /^\d{10}$/.test(c.cik) && /^\d{10}-\d{2}-\d{6}$/.test(acc)) {
    return `https://www.sec.gov/Archives/edgar/data/${Number(c.cik)}/${acc.replace(/-/g, "")}/`;
  }
  return null;
}

function Bar({ fraction, label, tone = "more" }: { fraction: number; label: string; tone?: "more" | "less" | "rewrite" }) {
  const fill = tone === "more" ? CHANGE_TONE.new.fill : tone === "less" ? CHANGE_TONE.removed.fill : CHANGE_TONE.materially_reworded.fill;
  return (
    <span className="flex items-center gap-3">
      <span aria-hidden="true" className="relative block h-2.5 w-full max-w-[240px] rounded-xs bg-sunken">
        <span className={`absolute inset-y-0 left-0 rounded-xs ${fill}`} style={{ width: `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%` }} />
      </span>
      <span className="whitespace-nowrap text-sm text-ink">{label}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------------------
// 1. Headline
// ---------------------------------------------------------------------------------------

function Headline({ data }: { data: TrendsPayload }) {
  const n = data.headline.companies;
  const m = data.headline.meaningful_changes;
  const top = headlineTopic(data.headline.top_topic);
  return (
    <header className="max-w-[80ch]">
      <h1 className="text-xl font-medium leading-tight tracking-tight text-ink">Trends across the library</h1>
      <p className="mt-4 text-lg font-medium leading-snug text-ink">
        Across {n} {n === 1 ? "company" : "companies"}, {m} risk {m === 1 ? "factor" : "factors"} changed meaningfully this year.
        {top ? (
          <>
            {" "}
            The most widespread new topic: {top.topic}, newly added by {top.company_count} of {n} companies.
          </>
        ) : (
          <span className="font-normal text-ink-secondary"> No topic was newly added by more than one company yet.</span>
        )}
      </p>
      <p className="mt-2 text-sm text-ink-secondary">These counts describe disclosure wording only, not how risky any company is.</p>
    </header>
  );
}

// ---------------------------------------------------------------------------------------
// 2. Topics several companies newly added
// ---------------------------------------------------------------------------------------

function TopicExample({ ex, company }: { ex: TrendsTopicExample; company: TrendsCompany | undefined }) {
  const { head, trimmed } = trimQuote(ex.text, 320);
  const url = edgarUrl(company, "new");
  return (
    <li className="min-w-0">
      <p className="text-sm text-ink-secondary">
        <Link href={`/c/${encodeURIComponent(ex.ticker)}`} className="font-medium text-ink underline-offset-2 hover:underline">
          {displayName(company?.name) || ex.ticker}
        </Link>
        {ex.short_title ? `, ${displayTitle(ex.short_title, null)}` : ""}
      </p>
      <blockquote className="quote is-new mt-1.5">
        <p>
          <SpanMarked text={ex.text} spans={ex.added_spans} limit={trimmed ? head.length : undefined} />
          {trimmed ? <span className="font-sans text-ink-secondary"> …</span> : null}
        </p>
      </blockquote>
      <p className="mt-2 flex flex-wrap gap-x-5 text-sm">
        {url ? (
          <FilingLink href={url.endsWith("/") ? url : textFragmentUrl(url, ex.text)} isFixture={false}>
            Open in SEC filing
          </FilingLink>
        ) : null}
        <Link href={`/c/${encodeURIComponent(ex.ticker)}/${encodeURIComponent(ex.change_id)}`} className="text-accent underline underline-offset-2">
          See the full change
        </Link>
      </p>
    </li>
  );
}

function TopicRow({ t, total, companies, open, withBar }: { t: TrendsTopic; total: number; companies: Map<string, TrendsCompany>; open?: boolean; withBar: boolean }) {
  const byTicker = new Map(t.examples.map((e) => [e.ticker, e] as const));
  const tag = SOURCE_TAG[t.source];
  const countLabel = `${t.company_count} of ${total} ${total === 1 ? "company" : "companies"}`;
  return (
    <details className="group border-b border-line py-3" open={open}>
      <summary className="grid cursor-pointer list-none items-center gap-x-6 gap-y-2 min-[900px]:grid-cols-[minmax(0,1.2fr)_minmax(0,1.4fr)_minmax(0,1.4fr)]">
        <span className="flex items-baseline gap-2">
          <span aria-hidden="true" className="text-ink-secondary transition group-open:rotate-90">
            ▸
          </span>
          <span className="text-base font-medium text-ink">{t.topic}</span>
          {tag ? <span className="text-sm text-ink-secondary">{tag}</span> : null}
        </span>
        {withBar ? <Bar fraction={total ? t.company_count / total : 0} label={countLabel} /> : <span className="text-sm text-ink">{countLabel}</span>}
        <span className="flex flex-wrap gap-1.5">
          {t.companies.map((ticker) => (
            <span key={ticker} className="rounded-sm bg-signal-bg px-2 py-0.5 text-xs text-ink-secondary">
              {displayName(companies.get(ticker)?.name) || ticker}
            </span>
          ))}
        </span>
      </summary>
      <ul className="mt-4 grid gap-6 pl-5 min-[900px]:grid-cols-2">
        {t.companies.map((ticker) => {
          const ex = byTicker.get(ticker);
          return ex ? <TopicExample key={ticker} ex={ex} company={companies.get(ticker)} /> : null;
        })}
      </ul>
    </details>
  );
}

function SharedTopics({ data }: { data: TrendsPayload }) {
  const [all, setAll] = useState(false);
  const companies = useMemo(() => new Map(data.companies.map((c) => [c.ticker, c] as const)), [data.companies]);
  const { shared, single } = useMemo(() => rankTopics(data.topics), [data.topics]);
  const total = data.headline.companies || data.companies.length;
  const list = shared.length > 0 ? shared : single;
  const shown = all ? list : list.slice(0, TOP_TOPICS);
  const withBar = list.some((t) => t.company_count !== list[0]?.company_count) || (list[0]?.company_count ?? 0) > 1;
  return (
    <section aria-labelledby="topics-heading" className="space-y-4">
      <SectionTitle
        id="topics-heading"
        aside={<span>{shared.length > 0 ? "Ranked by companies, then by new sentences" : "Each newly added by one company so far"}</span>}
      >
        {shared.length > 0 ? "Topics several companies newly added" : "New topics in the library"}
      </SectionTitle>
      {list.length === 0 ? (
        <p className="text-base text-ink-secondary">No topic was newly added this year by any company in the library.</p>
      ) : (
        <>
          <div className="border-t border-line">
            {shown.map((t, i) => (
              <TopicRow key={t.topic} t={t} total={total} companies={companies} open={i === 0} withBar={withBar} />
            ))}
          </div>
          {list.length > TOP_TOPICS ? (
            <button type="button" onClick={() => setAll((v) => !v)} className="text-sm text-accent underline underline-offset-2">
              {all ? `Show the top ${TOP_TOPICS}` : `Show all ${list.length} topics`}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// 3. Heatmap
// ---------------------------------------------------------------------------------------

// Heat tones are theme tokens (globals.css); intensity mixes them toward transparent.
const HEAT_VAR = { more: "var(--color-heat-more)", less: "var(--color-heat-less)", rewrite: "var(--color-heat-rewrite)" } as const;
const heat = (tone: keyof typeof HEAT_VAR, a: number) => `color-mix(in srgb, ${HEAT_VAR[tone]} ${Math.round(a * 100)}%, transparent)`;

function cellStyle(cell: HeatCell | undefined, maxActivity: number): { background: string; color: string } {
  const tone = cellTone(cell);
  if (tone === "empty") return { background: "transparent", color: "inherit" };
  const a = cellIntensity(cell, maxActivity);
  return { background: heat(tone, a), color: a > 0.55 ? "var(--color-heat-text-strong)" : "var(--color-heat-text)" };
}

function HeatmapLegend() {
  const steps: { tone: "less" | "rewrite" | "more"; a: number; label: string }[] = [
    { tone: "less", a: 0.9, label: "Far more removed" },
    { tone: "less", a: 0.4, label: "More removed" },
    { tone: "rewrite", a: 0.6, label: "Rewritten both ways" },
    { tone: "more", a: 0.4, label: "More added" },
    { tone: "more", a: 0.9, label: "Far more added" },
  ];
  return (
    <div className="space-y-2 text-sm text-ink-secondary">
      <ul className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Heatmap legend">
        {steps.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-4 w-7 rounded-xs" style={{ background: heat(s.tone, s.a) }} />
            {s.label}
          </li>
        ))}
      </ul>
      <p>
        Orange: more language removed than added in that area. Blue: more added. Gray: rewritten both ways. Stronger color means more sentences changed. The number in a
        cell is sentences changed. A risk factor tagged with two areas counts under both. The Change mix bars below count whole risk factors by kind of change, so one
        rewritten risk factor can add words in one area and remove them in another.
      </p>
    </div>
  );
}

function Heatmap({ data }: { data: TrendsPayload }) {
  const names = useMemo(() => new Map(data.companies.map((c) => [c.ticker, displayName(c.name) || c.ticker] as const)), [data.companies]);
  const hm = useMemo(() => buildHeatmap(data.category_activity, data.companies), [data.category_activity, data.companies]);
  const label = (c: string) => (c === OTHER_CATEGORY ? "Other" : categoryLabel(c));
  if (hm.columns.length === 0) {
    return (
      <section aria-labelledby="heatmap-heading" className="space-y-4">
        <SectionTitle id="heatmap-heading">How each risk area changed</SectionTitle>
        <p className="text-base text-ink-secondary">No category activity is available for these reports yet.</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="heatmap-heading" className="space-y-4">
      <SectionTitle id="heatmap-heading" aside={<span>Companies by risk area; a cell opens that company filtered to the area</span>}>
        How each risk area changed
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1 text-sm">
          <caption className="sr-only">Sentences changed per company and risk category, with the direction of change</caption>
          <thead>
            <tr>
              <th scope="col" className="min-w-[140px] text-left font-medium text-ink-secondary">
                Company
              </th>
              {hm.columns.map((c) => (
                <th key={c} scope="col" className="min-w-[72px] px-1 pb-1 text-left align-bottom font-normal leading-tight text-ink-secondary">
                  {label(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {hm.rows.map((r) => (
              <tr key={r.ticker}>
                <th scope="row" className="pr-3 text-left font-medium text-ink">
                  <Link href={`/c/${encodeURIComponent(r.ticker)}`} className="underline-offset-2 hover:underline">
                    {names.get(r.ticker) ?? r.ticker}
                  </Link>
                </th>
                {hm.columns.map((c) => {
                  const cell = r.cells.get(c);
                  const style = cellStyle(cell, hm.maxActivity);
                  if (!cell || cell.activity === 0) {
                    return (
                      <td key={c} className="h-11 rounded-sm bg-surface">
                        <span className="sr-only">
                          {names.get(r.ticker) ?? r.ticker}, {label(c)}: no sentences changed
                        </span>
                      </td>
                    );
                  }
                  const desc = cellDescription(names.get(r.ticker) ?? r.ticker, label(c), cell);
                  return (
                    <td key={c} className="h-11 rounded-sm p-0" style={style}>
                      <Link
                        href={`/c/${encodeURIComponent(r.ticker)}${c === OTHER_CATEGORY ? "" : `?topic=${encodeURIComponent(c)}`}`}
                        title={desc}
                        className="flex h-11 w-full items-center justify-center rounded-sm text-sm font-medium focus-visible:outline-offset-[-3px]"
                        style={{ color: style.color }}
                      >
                        <span aria-hidden="true">{cell.activity}</span>
                        <span className="sr-only">{desc}</span>
                      </Link>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <HeatmapLegend />
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// 4. Potential became actual, across the library
// ---------------------------------------------------------------------------------------

function ActualItem({ a, company }: { a: TrendsActual; company: TrendsCompany | undefined }) {
  const name = displayName(company?.name || a.company_name) || a.ticker;
  // Keep the marked words inside the window: extend the trim to the last marked span.
  const lastEnd = (spans: [number, number][]) => spans.reduce((m, [, b]) => Math.max(m, b), 0);
  const oldQ = a.old_text ? trimQuote(a.old_text, Math.max(200, Math.min(600, lastEnd(a.old_spans) + 40))) : null;
  const newQ = a.new_text ? trimQuote(a.new_text, Math.max(200, Math.min(600, lastEnd(a.new_spans) + 40))) : null;
  return (
    <li className="border-t border-line py-6">
      <div className="flex flex-wrap items-center gap-3">
        <ChangeBadge kind="potential_became_actual" size="sm" />
        <Link href={`/c/${encodeURIComponent(a.ticker)}`} className="text-sm text-ink-secondary underline-offset-2 hover:underline">
          {name}
        </Link>
      </div>
      <h3 className="mt-2 text-base font-medium text-ink">
        <Link href={`/c/${encodeURIComponent(a.ticker)}/${encodeURIComponent(a.change_id)}`} className="underline-offset-2 hover:underline">
          {displayTitle(a.short_title, null) || "See the change"}
        </Link>
      </h3>
      <div className="mt-3 grid gap-x-10 gap-y-3 min-[900px]:grid-cols-2">
        <div>
          <p className="mb-1 text-sm text-ink-secondary">Last year</p>
          {oldQ ? (
            <blockquote className="quote is-old text-base">
              <p>
                <SpanMarked text={a.old_text ?? ""} spans={a.old_spans} limit={oldQ.trimmed ? oldQ.head.length : undefined} mode="strike" />
                {oldQ.trimmed ? " …" : ""}
              </p>
            </blockquote>
          ) : (
            <p className="text-sm text-ink-muted">No matching sentence last year</p>
          )}
        </div>
        <div>
          <p className="mb-1 text-sm text-ink-secondary">This year</p>
          {newQ ? (
            <blockquote className="quote is-new text-base">
              <p>
                <SpanMarked text={a.new_text ?? ""} spans={a.new_spans} limit={newQ.trimmed ? newQ.head.length : undefined} />
                {newQ.trimmed ? " …" : ""}
              </p>
            </blockquote>
          ) : (
            <p className="text-sm text-ink-muted">No matching sentence this year</p>
          )}
        </div>
      </div>
    </li>
  );
}

function PotentialToActual({ data }: { data: TrendsPayload }) {
  const companies = useMemo(() => new Map(data.companies.map((c) => [c.ticker, c] as const)), [data.companies]);
  return (
    <section aria-labelledby="actual-heading" className="space-y-2">
      <SectionTitle id="actual-heading" aside={<span>Something described last year as possible is described this year as having happened</span>}>
        Potential became actual, across the library
      </SectionTitle>
      {data.potential_to_actual.length === 0 ? (
        <p className="pt-2 text-base text-ink-secondary">No risk factor in the library moved from potential to actual this year.</p>
      ) : (
        <ol>
          {data.potential_to_actual.map((a) => (
            <ActualItem key={`${a.ticker}-${a.change_id}-${a.new_sentence_id ?? ""}`} a={a} company={companies.get(a.ticker)} />
          ))}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// 5. Change mix by company
// ---------------------------------------------------------------------------------------

function ChangeMix({ data }: { data: TrendsPayload }) {
  const names = useMemo(() => new Map(data.companies.map((c) => [c.ticker, displayName(c.name) || c.ticker] as const)), [data.companies]);
  const rows = useMemo(
    () =>
      [...data.change_mix]
        .map((m) => ({ ...m, total: mixTotal(m.by_change_type) }))
        .sort((a, b) => b.total - a.total || a.ticker.localeCompare(b.ticker)),
    [data.change_mix],
  );
  const max = Math.max(1, ...rows.map((r) => r.total));
  return (
    <section aria-labelledby="mix-heading" className="space-y-4">
      <SectionTitle id="mix-heading">Change mix by company</SectionTitle>
      <ul className="border-t border-line">
        {rows.map((r) => (
          <li key={r.ticker} className="grid items-center gap-x-6 gap-y-1 border-b border-line py-3 min-[900px]:grid-cols-[160px_minmax(0,1fr)]">
            <Link href={`/c/${encodeURIComponent(r.ticker)}`} className="text-base font-medium text-ink underline-offset-2 hover:underline">
              {names.get(r.ticker) ?? r.ticker}
            </Link>
            <div>
              <div className="flex h-5 w-full gap-px" style={{ maxWidth: `${Math.round((r.total / max) * 100)}%` }} aria-hidden="true">
                {MIX_TYPES.map((t) => {
                  const n = r.by_change_type[t] ?? 0;
                  if (!n) return null;
                  return <span key={t} className={`block h-5 ${CHANGE_TONE[t].fill}`} style={{ flexGrow: n }} title={`${n} ${changeTypeVocab(t).label}`} />;
                })}
              </div>
              <p className="mt-1 text-sm text-ink-secondary">
                {r.total === 0
                  ? "No meaningful changes this year"
                  : MIX_TYPES.filter((t) => (r.by_change_type[t] ?? 0) > 0)
                      .map((t) => countedLabel(r.by_change_type[t], t))
                      .join(", ")}
              </p>
            </div>
          </li>
        ))}
      </ul>
      <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-secondary" aria-label="Legend">
        {MIX_TYPES.map((t) => (
          <span key={t} className="inline-flex items-center gap-2">
            <span aria-hidden="true" className={`inline-block h-3 w-3 rounded-xs ${CHANGE_TONE[t].fill}`} /> {changeTypeVocab(t).label}
          </span>
        ))}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------------------

function TrendsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <p className="sr-only" role="status">
        Connecting to the shared library.
      </p>
      <Skeleton className="h-8 w-[360px]" />
      <Skeleton className="h-6 w-[640px]" />
      <div className="space-y-3 pt-6">
        <Skeleton className="h-6 w-[300px]" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
      <p className="text-sm text-ink-secondary">Connecting to the shared library. This page updates on its own.</p>
    </div>
  );
}

function hasContent(d: TrendsPayload | null): d is TrendsPayload {
  return !!d && d.companies.length > 0;
}

export function TrendsView({ initial }: { initial: TrendsPayload | null }) {
  const [data, setData] = useState<TrendsPayload | null>(initial);
  const [gaveUp, setGaveUp] = useState(false);
  const connecting = !data || data.status === "connecting";

  useEffect(() => {
    if (!connecting || gaveUp) return;
    const started = Date.now();
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch("/api/trends", { cache: "no-store" });
        const next = parseTrends(await res.json());
        if (!cancelled && next) setData(next);
      } catch {
        /* keep the last payload */
      }
    };
    const timer = setInterval(() => {
      if (Date.now() - started > RETRY_FOR_MS) {
        setGaveUp(true);
        clearInterval(timer);
        return;
      }
      void tick();
    }, RETRY_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [connecting, gaveUp]);

  let body: React.ReactNode;
  if (hasContent(data) && data.companies.length >= 2) {
    body = (
      <div className="space-y-12">
        <Headline data={data} />
        <SharedTopics data={data} />
        <Heatmap data={data} />
        <PotentialToActual data={data} />
        <ChangeMix data={data} />
        <p className="border-t border-line pt-4 text-sm text-ink-secondary">{sourceLine(data)}</p>
      </div>
    );
  } else if (hasContent(data)) {
    body = (
      <>
        <h1 className="text-xl font-medium tracking-tight text-ink">Trends across the library</h1>
        <EmptyState title="Trends need at least two companies in the library.">
          <p>
            {data.companies.length} is published so far.{" "}
            <Link href="/" className="text-accent underline underline-offset-2">
              Back to the report library
            </Link>
          </p>
        </EmptyState>
      </>
    );
  } else if (connecting && !gaveUp) {
    body = <TrendsSkeleton />;
  } else {
    body = (
      <>
        <h1 className="text-xl font-medium tracking-tight text-ink">Trends across the library</h1>
        <EmptyState title="The shared library is not connected on this computer, so cross-company trends are not available.">
          <p>Reports on this computer still open from the home page.</p>
        </EmptyState>
      </>
    );
  }
  return <PageContainer className="space-y-6 py-10">{body}</PageContainer>;
}
