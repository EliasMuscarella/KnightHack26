"use client";

import { useRouter } from "next/navigation";
import { useId, useMemo, useState, useSyncExternalStore } from "react";

import { CompanyLogo } from "@/components/CompanyLogo";
import { cleanText, DEFAULT_TITLE, MAX_PREPARED_FOR_CHARS, MAX_TITLE_CHARS, selectionQuery } from "@/lib/briefing/selection";
import { MAX_BRIEFING_COMPANIES } from "@/lib/briefing/types";
import { TICKER_PATTERN } from "@/lib/ticker";

/** One library company, as the server page passes it in. */
export interface BriefingPickerCompany {
  ticker: string;
  name: string;
  oldFiscalYear: number;
  newFiscalYear: number;
  isFixture: boolean;
}

interface Draft {
  tickers: string[];
  title: string;
  preparedFor: string;
}

export const BRIEFING_STORAGE_KEY = "riskdiff-briefing";
const CHANGE_EVENT = "riskdiff-briefing-change";
const EMPTY: Draft = { tickers: [], title: "", preparedFor: "" };

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(BRIEFING_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Persist a draft (tickers, title, prepared for). Storage may be blocked: then the page simply forgets. */
export function writeBriefingDraft(draft: Draft) {
  try {
    window.localStorage.setItem(BRIEFING_STORAGE_KEY, JSON.stringify(draft));
    window.dispatchEvent(new Event(CHANGE_EVENT));
  } catch {
    // storage blocked or full: nothing to do
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Stored JSON is untrusted: keep only valid tickers from the library and capped strings. */
function parseDraft(raw: string | null, library: ReadonlySet<string>): Draft {
  if (!raw) return EMPTY;
  try {
    const v = JSON.parse(raw) as Partial<Record<keyof Draft, unknown>>;
    const tickers = Array.isArray(v.tickers)
      ? v.tickers.filter((t): t is string => typeof t === "string" && TICKER_PATTERN.test(t) && library.has(t)).slice(0, MAX_BRIEFING_COMPANIES)
      : [];
    const title = typeof v.title === "string" ? v.title.slice(0, MAX_TITLE_CHARS) : "";
    const preparedFor = typeof v.preparedFor === "string" ? v.preparedFor.slice(0, MAX_PREPARED_FOR_CHARS) : "";
    return { tickers: [...new Set(tickers)], title, preparedFor };
  } catch {
    return EMPTY;
  }
}

const inputClass =
  "h-11 w-full rounded-md border border-line-input bg-surface px-3 text-base text-ink placeholder:text-ink-secondary focus:border-accent focus:outline-none";
const secondaryButton =
  "h-9 cursor-pointer rounded-md border border-line-input bg-surface px-3 text-sm font-medium text-ink hover:border-ink disabled:cursor-not-allowed disabled:text-ink-muted disabled:hover:border-line-input";

export function BriefingPicker({ companies }: { companies: BriefingPickerCompany[] }) {
  const router = useRouter();
  const titleId = useId();
  const forId = useId();
  const countId = useId();
  const library = useMemo(() => new Set(companies.map((c) => c.ticker)), [companies]);

  // Storage is read after hydration only (the server snapshot is null), so markup always matches.
  const stored = useSyncExternalStore(subscribe, readRaw, () => null);
  const base = useMemo(() => parseDraft(stored, library), [stored, library]);
  const [edits, setEdits] = useState<Draft | null>(null);
  const draft = edits ?? base;
  const [busy, setBusy] = useState(false);

  const selected = new Set(draft.tickers);
  const full = selected.size >= MAX_BRIEFING_COMPANIES;

  function update(next: Draft) {
    setEdits(next);
    writeBriefingDraft(next);
  }

  function toggle(ticker: string, on: boolean) {
    const tickers = on ? (selected.has(ticker) || full ? draft.tickers : [...draft.tickers, ticker]) : draft.tickers.filter((t) => t !== ticker);
    update({ ...draft, tickers });
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    // Library order, so the same set of companies always gives the same link.
    const tickers = companies.map((c) => c.ticker).filter((t) => selected.has(t));
    if (tickers.length === 0) return;
    const title = cleanText(draft.title, MAX_TITLE_CHARS) || DEFAULT_TITLE;
    const preparedFor = cleanText(draft.preparedFor, MAX_PREPARED_FOR_CHARS) || null;
    setBusy(true);
    router.push(`/briefing?${selectionQuery({ tickers, title, preparedFor })}`);
  }

  if (companies.length === 0) {
    return <p className="text-base text-ink-secondary">The library has no companies yet. Analyze a company from the home page first.</p>;
  }

  return (
    // Without JavaScript the form still works: a GET to /briefing with tickers, title and for.
    <form action="/briefing" method="get" onSubmit={onSubmit} aria-label="Choose companies for the briefing" className="space-y-8">
      <fieldset>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <legend className="text-lg font-medium text-ink">Companies</legend>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={secondaryButton}
              onClick={() => update({ ...draft, tickers: companies.slice(0, MAX_BRIEFING_COMPANIES).map((c) => c.ticker) })}
            >
              Select all
            </button>
            <button type="button" className={secondaryButton} disabled={selected.size === 0} onClick={() => update({ ...draft, tickers: [] })}>
              Clear
            </button>
          </div>
        </div>
        <ul className="mt-4 grid gap-3 min-[900px]:grid-cols-3">
          {companies.map((c) => {
            const checked = selected.has(c.ticker);
            const disabled = !checked && full;
            return (
              <li key={c.ticker}>
                <label
                  className={`flex h-full items-center gap-3 rounded-lg border bg-surface px-4 py-3 transition ${
                    checked ? "border-ink" : "border-line"
                  } ${disabled ? "cursor-not-allowed" : "cursor-pointer hover:border-ink"}`}
                >
                  <input
                    type="checkbox"
                    name="tickers"
                    value={c.ticker}
                    checked={checked}
                    disabled={disabled}
                    onChange={(e) => toggle(c.ticker, e.target.checked)}
                    className="h-[18px] w-[18px] shrink-0 cursor-pointer accent-accent disabled:cursor-not-allowed"
                  />
                  <CompanyLogo ticker={c.ticker} name={c.name} size="sm" />
                  <span className="min-w-0">
                    <span className={`block truncate text-base font-medium leading-snug ${disabled ? "text-ink-muted" : "text-ink"}`}>{c.name}</span>
                    <span className="block text-sm text-ink-secondary">
                      {c.ticker}, FY{c.oldFiscalYear} → FY{c.newFiscalYear}
                      {c.isFixture ? ", fixture data" : ""}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      <div className="grid gap-6 min-[900px]:grid-cols-2">
        <div>
          <label htmlFor={titleId} className="block text-sm font-medium text-ink">
            Title
          </label>
          <input
            id={titleId}
            name="title"
            value={draft.title}
            onChange={(e) => update({ ...draft, title: e.target.value.slice(0, MAX_TITLE_CHARS) })}
            maxLength={MAX_TITLE_CHARS}
            placeholder={DEFAULT_TITLE}
            autoComplete="off"
            className={`mt-1.5 ${inputClass}`}
          />
        </div>
        <div>
          <label htmlFor={forId} className="block text-sm font-medium text-ink">
            Prepared for <span className="font-normal text-ink-secondary">(optional)</span>
          </label>
          <input
            id={forId}
            name="for"
            value={draft.preparedFor}
            onChange={(e) => update({ ...draft, preparedFor: e.target.value.slice(0, MAX_PREPARED_FOR_CHARS) })}
            maxLength={MAX_PREPARED_FOR_CHARS}
            placeholder="For example, Investment committee"
            autoComplete="off"
            className={`mt-1.5 ${inputClass}`}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line pt-6">
        <button
          type="submit"
          disabled={selected.size === 0 || busy}
          aria-describedby={countId}
          className="h-12 cursor-pointer rounded-md bg-accent px-6 text-base font-medium text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Preparing briefing…" : "Generate briefing"}
        </button>
        <p id={countId} className="text-sm text-ink-secondary" aria-live="polite">
          <span className="font-medium text-ink">{selected.size}</span> of {companies.length} selected, up to {MAX_BRIEFING_COMPANIES}
          {full ? <span className="text-ink-secondary">. Limit reached: clear one to pick another.</span> : null}
        </p>
      </div>
    </form>
  );
}
