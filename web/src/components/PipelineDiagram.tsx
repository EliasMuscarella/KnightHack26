import { STAGES } from "@/lib/stages";

function Arrow() {
  return (
    <svg aria-hidden="true" width="22" height="14" viewBox="0 0 22 14" className="text-ink-faint">
      <path d="M1 7h17M13 2l6 5-6 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Nine-stage pipeline as plain HTML/CSS boxes with inline SVG connectors. */
export function PipelineDiagram() {
  return (
    <figure className="rounded-lg border border-line bg-surface p-6">
      <div className="mb-4 flex items-center gap-6 text-xs font-semibold">
        <span className="inline-flex items-center gap-2 text-ink-muted">
          <span aria-hidden="true" className="inline-block h-3.5 w-5 rounded-sm border-2 border-ink-muted bg-surface" />
          Deterministic code
        </span>
        <span className="inline-flex items-center gap-2 text-ai-fg">
          <span aria-hidden="true" className="inline-block h-3.5 w-5 rounded-sm border-2 border-dashed border-ai-line bg-ai-bg" />
          <span aria-hidden="true">✦</span> AI-assisted (never decides what changed)
        </span>
      </div>
      <div className="flex items-stretch">
        <div className="flex w-[72px] shrink-0 flex-col items-center justify-center rounded-md bg-ink px-2 text-center text-xs font-semibold text-white">
          Ticker
          <span className="font-mono font-normal opacity-80">NVDA</span>
        </div>
        <ol className="flex flex-1 items-stretch" aria-label="Pipeline stages">
          {STAGES.map((s) => (
            <li key={s.stage} className="flex flex-1 items-center">
              <span className="flex w-[26px] shrink-0 justify-center">
                <Arrow />
              </span>
              <div
                className={`flex h-full min-h-[112px] flex-1 flex-col rounded-md p-2.5 ${
                  s.kind === "ai" ? "border-2 border-dashed border-ai-line bg-ai-bg" : "border-2 border-ink-muted bg-surface"
                }`}
              >
                <span className={`font-mono text-xs font-bold ${s.kind === "ai" ? "text-ai-fg" : "text-ink-faint"}`}>
                  {s.kind === "ai" ? "✦ " : ""}Stage {s.stage}
                </span>
                <span className="mt-1 text-sm font-semibold leading-snug text-ink">{s.label}</span>
                <span className={`mt-auto pt-2 text-[11px] font-semibold uppercase tracking-wide ${s.kind === "ai" ? "text-ai-fg" : "text-ink-faint"}`}>
                  {s.kind === "ai" ? "AI-assisted" : "Deterministic"}
                </span>
              </div>
            </li>
          ))}
          <li className="flex items-center">
            <span className="flex w-[26px] shrink-0 justify-center">
              <Arrow />
            </span>
            <div className="flex h-full w-[84px] flex-col items-center justify-center rounded-md bg-ink px-2 text-center text-xs font-semibold text-white">
              Published JSON
              <span className="font-mono font-normal opacity-80">cited</span>
            </div>
          </li>
        </ol>
      </div>
      <figcaption className="mt-4 text-sm text-ink-muted">
        Each stage is a pure function of its inputs and a stage version, cached on disk. Same filings and same versions
        produce byte-identical output and the same analysis id.
      </figcaption>
    </figure>
  );
}
