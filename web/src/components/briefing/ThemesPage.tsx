/** Page 2 of the Disclosure Briefing: shared themes (verbatim quotes) and the topic matrix. */
import type { BriefingModel, Theme, TopicMatrix } from "@/lib/briefing/types";

import { BriefingPage, changeLabel, Dot, EvidenceHead, FilingQuote, joinAnd, RULE_CLASS, SecLink } from "./parts";

function ThemeBlock({ theme, n }: { theme: Theme; n: number }) {
  const id = `bf-theme-${theme.topic.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  return (
    <section className="bf-section" aria-labelledby={id}>
      <h2 id={id} className="bf-h2">
        {theme.label}: new language at {theme.companyCount} of {n}
      </h2>
      <p className="bf-subline">Every quote is new this year and verbatim.</p>
      <div className="bf-grid2">
        {theme.quotes.map((q) => {
          const type = changeLabel(q.changeType);
          return (
            <div key={`${q.ticker}-${q.changeId}`} className={`bf-card ${q.changeType ? RULE_CLASS[q.changeType] : "border-line"}`}>
              <EvidenceHead
                name={q.name}
                sub={null}
                link={<SecLink href={q.edgarUrl} isFixture={q.isFixture} compact />}
              />
              <p className="bf-secondary bf-cardtitle">{type ? `${type}: ${q.shortTitle}` : q.shortTitle}</p>
              <FilingQuote quote={q.quote} side="new" status={q.quote.spans && q.quote.spans.length > 0 ? "modified" : "added"} />
            </div>
          );
        })}
      </div>
      {theme.alsoNamed.length > 0 ? (
        <p className="bf-strip">
          <span className="bf-strong">Also new this year:</span> {joinAnd(theme.alsoNamed)}.
        </p>
      ) : null}
    </section>
  );
}

function Matrix({ matrix, n }: { matrix: TopicMatrix; n: number }) {
  return (
    <section className="bf-section" aria-labelledby="bf-matrix">
      <h2 id="bf-matrix" className="bf-h2">
        Who added what this year
      </h2>
      <table className="bf-table bf-matrix">
        <thead>
          <tr>
            <th scope="col">Company</th>
            {matrix.topics.map((t) => (
              <th key={t.topic} scope="col" className="is-center">
                <span className="bf-block">{t.label}</span>
                <span className="bf-cell-sub">
                  {t.companyCount} of {n}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((r) => (
            <tr key={r.ticker}>
              <th scope="row">{r.name}</th>
              {r.hits.map((hit, i) => (
                <td key={matrix.topics[i]?.topic ?? i} className="is-center">
                  <Dot on={hit} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="bf-box">
        <p>
          <span className="bf-strong">How to read a blank.</span> A dot means the topic&apos;s wording appears in sentences added or
          changed this year and nowhere in that risk factor last year. A blank means no new language, not silence. A topic match is a
          keyword match, so read the quote before relying on a dot.
        </p>
      </div>
    </section>
  );
}

export function ThemesPage({ model }: { model: BriefingModel }) {
  const n = model.companies.length;
  return (
    <BriefingPage n={2} label="Themes across the list">
      {model.themes.map((t) => (
        <ThemeBlock key={t.topic} theme={t} n={n} />
      ))}
      {model.matrix ? <Matrix matrix={model.matrix} n={model.matrix.rows.length || n} /> : null}
    </BriefingPage>
  );
}
