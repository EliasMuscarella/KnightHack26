import { STAGES } from "@/lib/stages";

/** Nine-stage pipeline as a plain numbered row; AI-assisted stages are named, not colored. */
export function PipelineDiagram() {
  return (
    <figure>
      <p className="mb-3 text-sm text-ink-secondary">In: a ticker. Out: a published comparison JSON with every claim cited.</p>
      <ol className="grid grid-cols-3 gap-x-6 gap-y-4 min-[900px]:grid-cols-9" aria-label="Pipeline stages">
        {STAGES.map((s) => (
          <li key={s.stage} className="min-w-0 border-t border-ink pt-2">
            <span className="block text-sm text-ink-secondary">
              Stage {s.stage}
              {s.kind === "ai" ? ", AI-assisted" : ""}
            </span>
            <span className="mt-0.5 block text-sm font-medium leading-snug text-ink">{s.label}</span>
          </li>
        ))}
      </ol>
      <figcaption className="mt-4 max-w-prose-72 text-sm text-ink-secondary">
        Each stage is a pure function of its inputs and a stage version, cached on disk. Same filings and same versions produce
        byte-identical output and the same analysis id. AI-assisted stages never decide what changed.
      </figcaption>
    </figure>
  );
}
