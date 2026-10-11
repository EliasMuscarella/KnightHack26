/** Page 4 of the Disclosure Briefing: questions for management, the audit trail and the method. */
import type { BriefingModel } from "@/lib/briefing/types";
import { formatDate } from "@/lib/format";

import { BriefingPage, SecLink } from "./parts";

const HOW_PRODUCED = [
  "Both 10-K filings come from SEC EDGAR; amended filings (10-K/A) are excluded.",
  "Each risk factor is matched to last year's version, then compared sentence by sentence.",
  "The same two filings always produce the same analysis, so a result can be re-run and checked.",
  "'Changed meaningfully' covers new, dropped, expanded, scaled back and majorly updated risk factors.",
];

const DOES_NOT_DO = [
  "It does not rate risk, predict prices or recommend a trade.",
  "It reads the Risk Factors section only, not the financial statements or the management discussion.",
  "More language is not more risk. Lawyers add and remove wording for many reasons.",
  "Themes and the matrix come from keyword matching, not from reading.",
];

export function FollowUpsPage({ model, notes }: { model: BriefingModel; notes: string[] }) {
  return (
    <BriefingPage n={4} label="Follow-ups and audit trail">
      {model.questions.length > 0 ? (
        <section className="bf-section" aria-labelledby="bf-questions">
          <h2 id="bf-questions" className="bf-h2">
            Questions to raise with management
          </h2>
          <p className="bf-subline">
            Drafted from the changes cited in this briefing. Each one points at a specific risk factor so the answer can be checked
            against the filing.
          </p>
          <table className="bf-table bf-questions">
            <tbody>
              {model.questions.map((q) => (
                <tr key={`${q.ticker}-${q.changeId}`}>
                  <th scope="row" className="bf-strong">
                    {q.name}
                  </th>
                  <td>
                    <p>
                      <span className="bf-strong">{q.riskFactorTitle}</span> <span className="bf-secondary">({q.basis})</span>{" "}
                      {q.question}
                    </p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="bf-section" aria-labelledby="bf-audit">
        <h2 id="bf-audit" className="bf-h2">
          Audit trail
        </h2>
        <p className="bf-subline">
          Every quote in this briefing is verbatim from the filing listed here. The accession number is the SEC&apos;s permanent
          identifier for the filing and links to the document on EDGAR.
        </p>
        <table className="bf-table bf-audit">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Years compared</th>
              <th scope="col">Latest 10-K filed</th>
              <th scope="col">Accession number</th>
            </tr>
          </thead>
          <tbody>
            {model.audit.map((a) => (
              <tr key={a.ticker}>
                <th scope="row">
                  {a.name} <span className="bf-secondary">{a.ticker}</span>
                </th>
                <td className="bf-nowrap">{a.fyLabel}</td>
                <td className="bf-nowrap">{formatDate(a.latestFiled)}</td>
                <td>
                  <SecLink href={a.edgarUrl} isFixture={a.isFixture} compact>
                    <span className="bf-mono">{a.accession}</span>
                  </SecLink>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="bf-section bf-grid2" aria-label="Method">
        <div>
          <h3 className="bf-h3">How this was produced</h3>
          <ul className="bf-bullets">
            {HOW_PRODUCED.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="bf-h3">What this briefing does not do</h3>
          <ul className="bf-bullets">
            {DOES_NOT_DO.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </section>

      {model.fiscalYearNote ? <p className="bf-strip">{model.fiscalYearNote}</p> : null}
      {notes.length > 0 ? (
        <ul className="bf-notes">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      <p className="bf-meta">
        Briefing {model.briefingId.slice(0, 12)} · template {model.templateVersion} · generated {formatDate(model.generatedAt)}
      </p>
    </BriefingPage>
  );
}
