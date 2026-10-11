/** Page 1 of the Disclosure Briefing: the summary (title, stat tiles, read these first, coverage). */
import type { BriefingModel } from "@/lib/briefing/types";
import { formatDate } from "@/lib/format";

import { BriefingPage, fmt, joinAnd, MixBar, MixLegend, ReadFirstBadge, signed } from "./parts";

function Tile({ value, caption }: { value: string; caption: string }) {
  return (
    <div className="bf-tile">
      <p className="bf-tile-value">{value}</p>
      <p className="bf-tile-caption">{caption}</p>
    </div>
  );
}

function StatTiles({ model }: { model: BriefingModel }) {
  const h = model.headline;
  const hours = h.readingHours === 1 ? "hour" : "hours";
  const figures = h.newFigures.count === 0 ? "no new figures disclosed" : `newly disclosed figures: ${joinAnd(h.newFigures.examples)}`;
  return (
    <div className="bf-tiles">
      <Tile value={fmt(h.wordsThisYear)} caption={`words this year, about ${h.readingHours} ${hours} of reading`} />
      <Tile
        value={`${fmt(h.changed)} of ${fmt(h.totalRiskFactors)}`}
        caption={`risk factors changed meaningfully; ${fmt(h.unchanged)} are essentially unchanged`}
      />
      <Tile value={`${fmt(h.newCount)} new · ${fmt(h.droppedCount)} dropped`} caption="risk factors that appear in only one of the two years" />
      <Tile value={fmt(h.newFigures.count)} caption={figures} />
    </div>
  );
}

/** The lead is a label built from data; end it with a period so the support sentence reads apart. */
function closeSentence(text: string): string {
  const t = text.trim();
  return /[.!?:;…]$/.test(t) ? t : `${t}.`;
}

function ReadFirst({ model }: { model: BriefingModel }) {
  if (model.readFirst.length === 0) return null;
  return (
    <section className="bf-section" aria-labelledby="bf-read-first">
      <h2 id="bf-read-first" className="bf-h2">
        Read these first
      </h2>
      <ol className="bf-readfirst">
        {model.readFirst.map((item, i) => (
          <li key={`${item.kind}-${item.changeId ?? i}`} className="bf-readfirst-row">
            <span className="bf-readfirst-n" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <p>
                <ReadFirstBadge kind={item.kind} /> <span className="bf-strong">{closeSentence(item.lead)}</span>
                {item.support ? (
                  <>
                    {" "}
                    <span>{item.support}</span>
                    {item.supportSource === "validated_claim" ? <span className="sr-only"> (AI summary, citation-checked)</span> : null}
                  </>
                ) : null}
                {item.pageRef ? <span className="bf-secondary"> Page {item.pageRef}.</span> : null}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Coverage({ model }: { model: BriefingModel }) {
  return (
    <section className="bf-section" aria-labelledby="bf-coverage">
      <h2 id="bf-coverage" className="bf-h2">
        Coverage at a glance
      </h2>
      <table className="bf-table bf-coverage">
        <thead>
          <tr>
            <th scope="col">Company</th>
            <th scope="col" className="is-num">
              Changed
            </th>
            <th scope="col">Change mix, all risk factors</th>
            <th scope="col" className="is-num">
              New
            </th>
            <th scope="col" className="is-num">
              Dropped
            </th>
            <th scope="col" className="is-num">
              Words this year
            </th>
          </tr>
        </thead>
        <tbody>
          {model.coverage.map((r) => (
            <tr key={r.ticker}>
              <th scope="row">
                <span className="bf-strong">{r.name}</span>
                <span className="bf-cell-sub">
                  {r.ticker} · {r.fyLabel}
                </span>
              </th>
              <td className="is-num">
                <span className="bf-strong">{fmt(r.changed)}</span> of {fmt(r.total)}
              </td>
              <td>
                <MixBar mix={r.mix} total={r.total} />
              </td>
              <td className="is-num">{fmt(r.newCount)}</td>
              <td className="is-num">{fmt(r.droppedCount)}</td>
              <td className="is-num bf-nowrap">
                {fmt(r.wordsThisYear)}
                <span className="bf-delta" aria-label={`, ${signed(r.wordsDelta)} words from last year`}>
                  {signed(r.wordsDelta)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <MixLegend />
      <p className="bf-caption">
        Blue is more disclosure language, orange is less, gray is rewritten both ways. Colors show the direction of the wording, never
        whether a change is good or bad. The small figure after each word count is the change in section length from last year.
      </p>
    </section>
  );
}

export function SummaryPage({ model, movedNotes }: { model: BriefingModel; movedNotes: string[] }) {
  const n = model.companies.length;
  const asOf = model.libraryAsOf ? ` · library as of ${formatDate(model.libraryAsOf)}` : "";
  return (
    <BriefingPage n={1} label="Built from the RiskDiff report library">
      <div className="bf-titleblock">
        <h1 className="bf-title">{model.title}</h1>
        {model.preparedFor ? <p className="bf-prepared">Prepared for {model.preparedFor}</p> : null}
        <p className="bf-subtitle">
          What changed in the Risk Factors sections of the latest annual reports (10-K), against the year before. {n}{" "}
          {n === 1 ? "company" : "companies"}
          {asOf} · page 1 is the summary, pages 2 to 4 are the evidence.
        </p>
        {model.missingTickers.length > 0 ? (
          <p className="bf-secondary">Not in the report library, so not in this briefing: {model.missingTickers.join(", ")}.</p>
        ) : null}
      </div>
      <StatTiles model={model} />
      <ReadFirst model={model} />
      <Coverage model={model} />
      {movedNotes.length > 0 ? (
        <ul className="bf-notes">
          {movedNotes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </BriefingPage>
  );
}
