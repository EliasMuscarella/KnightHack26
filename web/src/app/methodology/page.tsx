import type { Metadata } from "next";

import { Markdown } from "@/components/Markdown";
import { PipelineDiagram } from "@/components/PipelineDiagram";
import { EmptyState, PageContainer } from "@/components/ui";
import { getEvalMarkdown, getRubric } from "@/lib/data";
import { STAGES } from "@/lib/stages";
import { CHANGE_LEVEL, LEVEL_HIGH_MIN, LEVEL_MEDIUM_MIN, scoreLineLabel } from "@/lib/vocabulary";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Methodology" };

const NEVER = [
  "Never decides what changed with a language model. Diffs, change types and scores are deterministic code.",
  "Never shows an AI claim without a valid citation to filing sentences. Uncited or invalid claims are dropped before publishing.",
  "Never characterizes a company's overall risk level, and never turns a disclosure change into a risk percentage.",
  "Never gives trading or portfolio advice, and never suggests acting on a disclosure change.",
  "Never fabricates filings, sentences or numbers. The development fixture is labeled on every screen and is never published.",
  "Never renders filing text as HTML. Filing text is displayed as plain text only.",
  "Never re-downloads a cached filing, and stays within SEC fair-access limits.",
];

/** Neutral descriptions of the blocked-wording groups (the phrases themselves are not shown). */
const BLOCKED_CATEGORIES = [
  "predictive wording about whether or when an event occurs",
  "advice wording about trading or allocating money",
  "comparative wording about a company's overall level of risk or safety",
  "assurances about outcomes",
];

const PLAIN_STEPS = [
  {
    title: "Pull both filings from SEC EDGAR",
    body: "The company's two most recent annual reports (10-K), straight from the SEC. Amendments are excluded.",
    ai: false,
  },
  {
    title: "Match each risk factor to last year's version",
    body: "Each risk is paired with its counterpart from last year, even when it moved or was renamed. Unpaired risks are new or dropped.",
    ai: true,
  },
  {
    title: "Find the exact sentences that changed",
    body: "Sentence by sentence and word by word: what was added, removed, or rewritten.",
    ai: false,
  },
  {
    title: "Summarize, with every statement cited",
    body: "A short plain-English summary of each change. Every point links to the filing sentences behind it.",
    ai: true,
  },
];

const DOES_NOT = [
  {
    title: "No predictions",
    body: "It reports what the filings say. It never forecasts events or outcomes.",
  },
  {
    title: "No risk ratings",
    body: "A change in disclosure language is not a change in actual risk. The wording change level measures wording only.",
  },
  {
    title: "No investment advice",
    body: "It never suggests acting on a disclosure change.",
  },
];

function Section({ id, title, children, lead }: { id: string; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-5 border-t border-line pt-6">
      <div>
        <h2 id={id} className="text-lg font-medium text-ink">
          {title}
        </h2>
        {lead ? <p className="mt-1 max-w-prose-72 text-base text-ink-secondary">{lead}</p> : null}
      </div>
      {children}
    </section>
  );
}

export default async function MethodologyPage() {
  const [rubric, evalMd] = await Promise.all([getRubric(), getEvalMarkdown()]);

  return (
    <PageContainer className="space-y-12 py-10">
      <header className="max-w-prose-72">
        <h1 className="text-xl font-title tracking-tight text-ink">How RiskDiff works</h1>
        <p className="mt-4 text-base leading-relaxed text-ink-secondary">
          Every year a public company lists the risks it faces in the Risk Factors section of its annual report (10-K).
          RiskDiff lines up this year&apos;s list against last year&apos;s and shows exactly which sentences changed. The
          filing text is the only evidence: every quote is verbatim, and every AI statement points to the sentences it
          is based on.
        </p>
      </header>

      <Section id="how" title="Four steps">
        <ol className="grid gap-x-10 gap-y-6 min-[900px]:grid-cols-4" aria-label="Four steps">
          {PLAIN_STEPS.map((step, i) => (
            <li key={step.title} className="min-w-0 border-t border-ink pt-3">
              <p className="text-sm text-ink-secondary">
                Step {i + 1}
                {step.ai ? ", with AI" : ""}
              </p>
              <p className="mt-1 text-base font-medium leading-snug text-ink">{step.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-ink-secondary">{step.body}</p>
            </li>
          ))}
        </ol>
        <p className="max-w-prose-72 text-base text-ink-secondary">
          What changed is always computed by fixed rules in code, so the same two filings always give the same
          result. AI helps in three narrow places only: recognizing that a reworded risk is the same risk as last
          year&apos;s (step 2), wording short summaries (step 4), and answering four fixed yes/no questions about each
          change. A &ldquo;yes&rdquo; adds a fixed, published number of points only when it cites the filing sentences
          behind it, and never when a rule in code already scored the same fact. Any summary statement that does not cite valid
          filing sentences is removed before it is shown. Each change also gets a {CHANGE_LEVEL.label.toLowerCase()} (High {LEVEL_HIGH_MIN}+, Medium{" "}
          {LEVEL_MEDIUM_MIN}–{LEVEL_HIGH_MIN - 1}, Low below {LEVEL_MEDIUM_MIN}, on a 0 to 100 scale): {CHANGE_LEVEL.helper.charAt(0).toLowerCase() + CHANGE_LEVEL.helper.slice(1)}
        </p>
      </Section>

      <Section id="does-not" title="What RiskDiff does not do">
        <ul className="grid max-w-[1000px] gap-x-10 gap-y-4 min-[900px]:grid-cols-3">
          {DOES_NOT.map((item) => (
            <li key={item.title} className="text-base leading-relaxed text-ink">
              <span className="font-medium">{item.title}.</span> <span className="text-ink-secondary">{item.body}</span>
            </li>
          ))}
        </ul>

      </Section>

      <details className="group border-t border-line pt-6" id="technical-detail">
        <summary className="flex cursor-pointer list-none items-baseline gap-3 rounded-md">
          <span aria-hidden="true" className="text-ink-secondary transition group-open:rotate-90">
            ▸
          </span>
          <span>
            <span className="block text-lg font-medium text-ink">Technical detail</span>
            <span className="mt-1 block max-w-prose-72 text-sm text-ink-secondary">
              The full pipeline, the published scoring weights, thresholds and caps, blocked wording, and the
              evaluation status. RiskDiff reads Item 1A (Risk Factors) of each 10-K.
            </span>
          </span>
        </summary>
        <div className="mt-8 space-y-12">
        <Section id="pipeline" title="The pipeline (nine stages)" lead="Nine stages. Seven are deterministic code; two use models, and neither decides what changed.">
          <PipelineDiagram />
          <ol className="grid gap-x-8 gap-y-4 text-sm min-[900px]:grid-cols-3">
            {STAGES.map((s) => (
              <li key={s.stage} className="border-t border-line pt-3">
                <p className="font-medium text-ink">
                  <span className="text-ink-secondary">{s.stage}.</span> {s.label}
                  {s.kind === "ai" ? <span className="text-ink-secondary"> (AI-assisted)</span> : null}
                </p>
                <p className="mt-1 leading-relaxed text-ink-secondary">{s.description}</p>
              </li>
            ))}
          </ol>
        </Section>

        <Section
          id="scoring"
          title="Scoring weights"
          lead={`Each change gets a 0 to 100 score: a sum of published weights for signals that fired, each with cited sentences. It is shown as a change level (High at ${LEVEL_HIGH_MIN} or more, Medium from ${LEVEL_MEDIUM_MIN}, Low below ${LEVEL_MEDIUM_MIN}). It ranks how much the disclosure language changed and is not a measure of risk.`}
        >
          {rubric ? (
            <div className="space-y-6">
              <p className="text-sm text-ink-secondary">
                Rubric version <span className="font-mono text-ink">{rubric.rubric_version}</span>, pipeline version{" "}
                <span className="font-mono text-ink">{rubric.pipeline_version}</span>, source <span className="font-mono">contract/rubric.json</span>
              </p>
              <div className="overflow-hidden rounded-lg border border-line bg-surface">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Score weights per signal</caption>
                  <thead className="bg-sunken text-sm text-ink-secondary">
                    <tr>
                      <th scope="col" className="px-4 py-2">Signal</th>
                      <th scope="col" className="px-4 py-2">Label</th>
                      <th scope="col" className="px-4 py-2">Shown as</th>
                      <th scope="col" className="px-4 py-2 text-right">Points</th>
                      <th scope="col" className="px-4 py-2">What it means</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rubric.weights.map((w) => (
                      <tr key={w.signal} className="border-t border-line align-top">
                        <td className="px-4 py-2.5 font-mono text-sm text-ink-secondary">{w.signal}</td>
                        <td className="px-4 py-2.5 font-medium text-ink">{w.label}</td>
                        <td className="px-4 py-2.5 text-ink-secondary">{scoreLineLabel(w.signal, "", w.label)}</td>
                        <td className="px-4 py-2.5 text-right font-medium text-ink">{w.points}</td>
                        <td className="max-w-[60ch] px-4 py-2.5 leading-relaxed text-ink-secondary">{w.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rubric.questions.length > 0 ? (
                <div className="overflow-hidden rounded-lg border border-line bg-surface">
                  <table className="w-full text-left text-sm">
                    <caption className="bg-signal-bg px-4 py-2 text-left text-sm font-medium text-ink">
                      AI rubric questions (a yes counts only with a valid citation)
                    </caption>
                    <thead className="bg-sunken text-sm text-ink-secondary">
                      <tr>
                        <th scope="col" className="px-4 py-2">Id</th>
                        <th scope="col" className="px-4 py-2">Question</th>
                        <th scope="col" className="px-4 py-2 text-right">Points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rubric.questions.map((q) => (
                        <tr key={q.id} className="border-t border-line align-top">
                          <td className="px-4 py-2.5 font-mono text-sm text-ink-secondary">{q.id}</td>
                          <td className="max-w-[80ch] px-4 py-2.5 leading-relaxed text-ink">{q.text}</td>
                          <td className="px-4 py-2.5 text-right font-medium text-ink">{q.points}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              <div className="grid gap-x-10 gap-y-6 min-[900px]:grid-cols-3">
                {Object.keys(rubric.thresholds).length > 0 ? (
                  <div className="border-t border-line pt-3">
                    <h3 className="text-sm font-medium text-ink">Thresholds</h3>
                    <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-sm">
                      {Object.entries(rubric.thresholds).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="font-mono text-xs text-ink-secondary">{k}</dt>
                          <dd className="text-right font-mono tabular-nums text-ink">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ) : null}
                {Object.keys(rubric.caps).length > 0 ? (
                  <div className="border-t border-line pt-3">
                    <h3 className="text-sm font-medium text-ink">Score caps</h3>
                    <p className="mt-1 text-xs leading-snug text-ink-secondary">
                      Upper limits applied while adding up points, so repeated hits of one signal cannot dominate a
                      change score.
                    </p>
                    <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-sm">
                      {Object.entries(rubric.caps).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="font-mono text-xs text-ink-secondary">{k}</dt>
                          <dd className="text-right font-mono tabular-nums text-ink">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ) : null}
                {rubric.banned_phrases.length > 0 ? (
                  <div className="border-t border-line pt-3 text-sm">
                    <h3 className="font-medium text-ink">Wording the citation validator blocks</h3>
                    <p className="mt-2 text-ink-secondary">
                      The validator checks every AI claim against a list of {rubric.banned_phrases.length} blocked phrases
                      and removes any claim that uses one before publishing. The list covers:
                    </p>
                    <ul className="mt-2 list-disc space-y-0.5 pl-5 text-ink-secondary">
                      {BLOCKED_CATEGORIES.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                    <p className="mt-2 text-xs text-ink-secondary">
                      The exact list is in <span className="font-mono">contract/rubric.json</span>; it is not repeated here.
                    </p>
                  </div>
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
          <p className="max-w-prose-72 text-base text-ink-secondary">
            Evaluation runs on the team&apos;s machine with real filings; this section shows the latest saved results.
          </p>
          <details className="group/eval">
            <summary className="flex cursor-pointer list-none items-baseline gap-3">
              <span aria-hidden="true" className="text-ink-secondary transition group-open/eval:rotate-90">
                ▸
              </span>
              <span className="text-base font-medium text-ink">Evaluation status</span>
              <span className="text-sm text-ink-secondary">EVAL.md: matcher precision and recall, thresholds, determinism</span>
            </summary>
            <div className="mt-4">
              {evalMd ? (
                <Markdown source={evalMd} />
              ) : (
                <EmptyState title="Evaluation not yet run.">
                  <p>
                    Results are written to <code className="rounded bg-sunken px-1 font-mono text-sm">EVAL.md</code> by{" "}
                    <code className="rounded bg-sunken px-1 font-mono text-sm">uv run python -m eval.eval</code>. No numbers
                    are shown until a real evaluation exists.
                  </p>
                </EmptyState>
              )}
            </div>
          </details>
        </Section>

        <Section id="never" title="What RiskDiff never does">
          <ul className="grid max-w-[1000px] gap-x-10 gap-y-3 min-[900px]:grid-cols-2">
            {NEVER.map((item) => (
              <li key={item} className="border-t border-line pt-2 text-sm leading-relaxed text-ink">
                {item}
              </li>
            ))}
          </ul>
        </Section>
        </div>
      </details>
    </PageContainer>
  );
}
