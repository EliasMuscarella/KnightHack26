"use client";

/**
 * The home hero's specimen: a card that cycles through real before/after sentences from the library,
 * one per kind of change, so a first-time visitor sees what RiskDiff marks. Each slide plays once:
 * last year's sentence, the struck words, then this year's sentence with the highlighter drawn over
 * the new words (globals.css `.specimen-slide`). Every sentence is verbatim from a filing.
 *
 * All slides sit in one grid cell, so the card is as tall as the tallest slide and nothing shifts;
 * the inactive ones are invisible, inert and hidden from screen readers. Auto-advance stops while the
 * pointer or focus is inside, when the visitor pauses it, and under prefers-reduced-motion (the slides
 * then change only through the dots).
 */
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Quote } from "@/components/Quote";
import { ChangeBadge } from "@/components/ui";
import { neutralizeCaseOnly } from "@/lib/diffDisplay";
import type { Specimen, SpecimenSide } from "@/lib/specimen";
import { MAX_SIDE_CHARS } from "@/lib/specimen";
import { displayTitle, isCompanyName } from "@/lib/vocabulary";

const HOLD_MS = 7000;
const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReduced(onChange: () => void): () => void {
  const mq = window.matchMedia(REDUCED_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

function absent(kind: Specimen["kind"]): { old: string; new: string } {
  return {
    old:
      kind === "new_risk"
        ? "Not in last year's filing"
        : kind === "new_named_party"
          ? "This name did not appear last year"
          : kind === "new_figure"
            ? "This figure did not appear last year"
            : "No matching sentence last year",
    new: kind === "removed_risk" ? "Removed this year" : "No matching sentence this year",
  };
}

function SideQuote({ side, which, pair }: { side: SpecimenSide; which: "old" | "new"; pair: ReturnType<typeof neutralizeCaseOnly> | null }) {
  return (
    <Quote
      text={side.text}
      side={which}
      status={side.status}
      spans={pair ? pair[which] : side.spans}
      sourceSpans={side.spans}
      max={MAX_SIDE_CHARS + 40}
    />
  );
}

function Slide({ s, active }: { s: Specimen; active: boolean }) {
  const none = absent(s.kind);
  const pair = s.old?.status === "modified" && s.new?.status === "modified" ? neutralizeCaseOnly(s.old.spans, s.new.spans) : null;
  const title = displayTitle(s.shortTitle, s.title);
  const showTitle = !!title && !isCompanyName(title, s.company);
  const detail = s.kind === "new_named_party" || s.kind === "new_figure" ? s.detail : null;
  return (
    <div
      className={`specimen-slide ${active ? "draw-marks" : "invisible"}`}
      style={{ gridArea: "1 / 1" }}
      aria-hidden={active ? undefined : true}
      inert={!active}
    >
      <div className="mb-4">
        <ChangeBadge kind={s.kind} figureChanged={s.figureChanged} detail={detail} />
      </div>
      <div className="specimen-old">
        <p className="mb-1.5 text-sm text-ink-secondary">Last year, FY{s.oldFY}</p>
        {s.old ? <SideQuote side={s.old} which="old" pair={pair} /> : <p className="text-base text-ink-muted">{none.old}</p>}
      </div>
      <div className="specimen-new mt-5">
        <p className="mb-1.5 text-sm text-ink-secondary">This year, FY{s.newFY}</p>
        {s.new ? <SideQuote side={s.new} which="new" pair={pair} /> : <p className="text-base text-ink-muted">{none.new}</p>}
      </div>
      <p className="mt-5 text-sm text-ink-secondary">
        <span className="font-medium text-ink">{s.company}</span>
        {showTitle ? `, ${title}` : ""}.{" "}
        <Link href={`/c/${s.ticker}/${s.changeId}`} className="text-accent underline underline-offset-2">
          See the full change
        </Link>
      </p>
    </div>
  );
}

export function HeroSpecimen({ slides }: { slides: Specimen[] }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [inside, setInside] = useState(false);
  // Server and first client render assume motion is fine; the store then reports the real preference.
  const reduced = useSyncExternalStore(subscribeReduced, () => window.matchMedia(REDUCED_QUERY).matches, () => false);

  const running = slides.length > 1 && !paused && !inside && !reduced;
  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(() => setIndex((i) => (i + 1) % slides.length), HOLD_MS);
    return () => window.clearTimeout(t);
  }, [running, index, slides.length]);

  if (slides.length === 0) return null;
  return (
    <section
      aria-roledescription="carousel"
      aria-label="Examples of what changed"
      className="rounded-lg border border-line bg-paper p-6"
      onMouseEnter={() => setInside(true)}
      onMouseLeave={() => setInside(false)}
      onFocus={() => setInside(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setInside(false);
      }}
    >
      <p className="mb-4 text-sm text-ink-secondary">Real sentences from the library. New words carry the highlighter; removed words are struck.</p>
      <div className="grid">
        {slides.map((s, i) => (
          <Slide key={`${s.ticker}-${s.changeId}-${s.kind}`} s={s} active={i === index} />
        ))}
      </div>
      {slides.length > 1 ? (
        <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <div className="flex items-center gap-2" role="group" aria-label="Choose an example">
            {slides.map((s, i) => (
              <button
                key={`${s.ticker}-${s.changeId}-${s.kind}`}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Example ${i + 1} of ${slides.length}: ${s.company}`}
                aria-current={i === index ? "true" : undefined}
                className="flex h-6 w-6 items-center justify-center"
              >
                <span className={`block h-2.5 w-2.5 rounded-full border border-ink-secondary ${i === index ? "bg-ink" : "bg-transparent"}`} />
              </button>
            ))}
          </div>
          {reduced ? null : (
            <button type="button" onClick={() => setPaused((p) => !p)} aria-pressed={paused} className="text-sm font-medium text-accent underline underline-offset-2">
              {paused ? "Play" : "Pause"}
            </button>
          )}
        </div>
      ) : null}
    </section>
  );
}
