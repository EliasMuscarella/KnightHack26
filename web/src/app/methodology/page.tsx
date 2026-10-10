import type { Metadata } from "next";

import { Markdown } from "@/components/Markdown";
import { PipelineDiagram } from "@/components/PipelineDiagram";
import { EmptyState, PageContainer } from "@/components/ui";
import { DISCLAIMER } from "@/lib/copy";
import { getEvalMarkdown, getRubric } from "@/lib/data";
import { STAGES } from "@/lib/stages";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Methodology" };

const NEVER = [
  "Never decides what changed with a language model. Diffs, change types and scores are deterministic code.",
  "Never shows an AI claim without a valid citation to filing sentences. Uncited or invalid claims are dropped before publishing.",
  "Never says a company became more or less risky, and never turns a disclosure change into a risk percentage.",
  "Never gives investment advice or suggests trading on a disclosure change.",
  "Never fabricates filings, sentences or numbers. The development fixture is labeled on every screen and is never published.",
  "Never renders filing text as HTML. Filing text is displayed as plain text only.",
  "Never re-downloads a cached filing, and stays within SEC fair-access limits.",
];

function Section({ id, title, children, lead }: { id: string; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-4">
      <div>
        <h2 id={id} className="text-2xl font-bold tracking-tight text-ink">
          {title}
        </h2>
        {lead ? <p className="mt-1 max-w-[75ch] text-ink-muted">{lead}</p> : null}
      </div>
      {children}
    </section>
  );
}

export default async function MethodologyPage() {
  const [rubric, evalMd] = await Promise.all([getRubric(), getEvalMarkdown()]);

  return (
    <PageContainer className="space-y-14 py-10">
      <header className="max-w-[80ch]">
        <p className="font-mono text-sm font-semibold uppercase tracking-widest text-ink-faint">Methodology</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-ink">How RiskDiff works</h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-muted">
          RiskDiff treats SEC filing text as the only source of truth. It finds Item 1A in a company&apos;s two most
          recent original 10-K filings, aligns equivalent risk factors across the two years, and computes a
          sentence-level and word-level diff. AI assists with alignment and short cited interpretations, but never
          decides facts.
        </p>
        <div role="note" className="mt-6 rounded-md border-2 border-ink bg-surface px-5 py-4 text-base font-semibold text-ink">
          <span aria-hidden="true">ⓘ </span>
          {DISCLAIMER}
        </div>
      </header>

      <Section id="pipeline" title="The pipeline" lead="Nine stages. Seven are deterministic code; two use models, and neither decides what changed.">
        <PipelineDiagram />
        <ol className="grid grid-cols-3 gap-4">
          {STAGES.map((s) => (
            <li key={s.stage} className={`rounded-md border p-4 text-sm ${s.kind === "ai" ? "border-dashed border-ai-line bg-ai-bg" : "border-line bg-surface"}`}>
              <p className="font-semibold text-ink">
                <span className="font-mono text-ink-faint">{s.stage}</span> {s.label}
                {s.kind === "ai" ? <span className="text-xs text-ai-fg"> · ✦ AI-assisted</span> : null}
              </p>
              <p className="mt-1 leading-relaxed text-ink-muted">{s.description}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        id="scoring"
        title="Scoring weights"
        lead="Each change gets a 0 to 100 change score: a sum of published weights for signals that fired, each with cited sentences. The score ranks how much the disclosure language changed. It is not a measure of risk."
      >
        {rubric ? (
          <div className="space-y-6">
            <p className="text-sm text-ink-faint">
              Rubric version <span className="font-mono text-ink">{rubric.rubric_version}</span> · pipeline version{" "}
              <span className="font-mono text-ink">{rubric.pipeline_version}</span> · source{" "}
              <span className="font-mono">contract/rubric.json</span>
            </p>
            <div className="overflow-hidden rounded-lg border border-line bg-surface">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Score weights per signal</caption>
                <thead className="bg-sunken text-xs uppercase tracking-wide text-ink-faint">
                  <tr>
                    <th scope="col" className="px-4 py-2">Signal</th>
                    <th scope="col" className="px-4 py-2">Label</th>
                    <th scope="col" className="px-4 py-2 text-right">Points</th>
                    <th scope="col" className="px-4 py-2">What it means</th>
                  </tr>
                </thead>
                <tbody>
                  {rubric.weights.map((w) => (
                    <tr key={w.signal} className="border-t border-line align-top">
                      <td className="px-4 py-2.5 font-mono text-xs text-ink-muted">{w.signal}</td>
                      <td className="px-4 py-2.5 font-medium text-ink">{w.label}</td>
                      <td className="px-4 py-2.5 text-right font-mono font-semibold tabular-nums text-ink">{w.points}</td>
                      <td className="max-w-[60ch] px-4 py-2.5 leading-relaxed text-ink-muted">{w.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rubric.questions.length > 0 ? (
              <div className="overflow-hidden rounded-lg border border-ai-line/50 bg-surface">
                <table className="w-full text-left text-sm">
                  <caption className="bg-ai-bg px-4 py-2 text-left text-sm font-semibold text-ai-fg">
                    <span aria-hidden="true">✦ </span>AI rubric questions (a yes counts only with a valid citation)
                  </caption>
                  <thead className="bg-sunken text-xs uppercase tracking-wide text-ink-faint">
                    <tr>
                      <th scope="col" className="px-4 py-2">Id</th>
                      <th scope="col" className="px-4 py-2">Question</th>
                      <th scope="col" className="px-4 py-2 text-right">Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rubric.questions.map((q) => (
                      <tr key={q.id} className="border-t border-line align-top">
                        <td className="px-4 py-2.5 font-mono text-xs text-ink-muted">{q.id}</td>
                        <td className="max-w-[80ch] px-4 py-2.5 leading-relaxed text-ink">{q.text}</td>
                        <td className="px-4 py-2.5 text-right font-mono font-semibold tabular-nums text-ink">{q.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <div className="grid grid-cols-2 gap-6">
              {Object.keys(rubric.thresholds).length > 0 ? (
                <div className="rounded-lg border border-line bg-surface p-4">
                  <h3 className="text-sm font-bold text-ink">Thresholds</h3>
                  <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-sm">
                    {Object.entries(rubric.thresholds).map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="font-mono text-xs text-ink-muted">{k}</dt>
                        <dd className="text-right font-mono tabular-nums text-ink">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : null}
              {rubric.banned_phrases.length > 0 ? (
                <details className="rounded-lg border border-line bg-surface p-4 text-sm">
                  <summary className="cursor-pointer font-bold text-ink">
                    Phrases the citation validator blocks ({rubric.banned_phrases.length})
                  </summary>
                  <p className="mt-2 text-ink-muted">
                    Any AI claim containing one of these phrases is removed before publishing.
                  </p>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {rubric.banned_phrases.map((p) => (
                      <li key={p} className="rounded bg-sunken px-1.5 py-px font-mono text-xs text-ink-muted line-through">
                        {p}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          </div>
        ) : (
          <EmptyState title="Scoring weights not yet generated.">
            <p>
              The pipeline exports its weights, rubric questions and thresholds to{" "}
              <code className="rounded bg-sunken px-1 font-mono text-sm">contract/rubric.json</code>. This table will
              appear once that file exists. Every published comparison still carries its own itemized score breakdown.
            </p>
          </EmptyState>
        )}
      </Section>

      <Section id="evaluation" title="Evaluation" lead="Matcher precision and recall on hand-labeled filing pairs, threshold calibration, and determinism checks.">
        {evalMd ? (
          <div className="rounded-lg border border-line bg-surface p-6">
            <Markdown source={evalMd} />
          </div>
        ) : (
          <EmptyState title="Evaluation not yet run.">
            <p>
              Results are written to <code className="rounded bg-sunken px-1 font-mono text-sm">EVAL.md</code> by{" "}
              <code className="rounded bg-sunken px-1 font-mono text-sm">uv run python -m eval.eval</code>. No numbers
              are shown until a real evaluation exists.
            </p>
          </EmptyState>
        )}
      </Section>

      <Section id="never" title="What RiskDiff never does">
        <ul className="grid max-w-[1000px] grid-cols-2 gap-3">
          {NEVER.map((item) => (
            <li key={item} className="flex gap-3 rounded-md border border-line bg-surface p-4 text-sm leading-relaxed text-ink">
              <span aria-hidden="true" className="font-mono font-bold text-del-fg">
                ✕
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </Section>
    </PageContainer>
  );
}
