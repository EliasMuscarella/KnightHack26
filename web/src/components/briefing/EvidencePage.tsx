/**
 * Page 3 of the Disclosure Briefing: what became real (potential → actual), new figures, new and
 * dropped risk factors, and the quiet companies listed for completeness.
 */
import type { BeforeAfterQuote, BriefingModel, QuietCompany, RiskListItem } from "@/lib/briefing/types";
import { CHANGE_TONE } from "@/lib/vocabulary";

import { ActualBadge, BeforeAfter, BriefingPage, detailLabel, EvidenceHead, FilingQuote, fmt, Pill, QuoteLink } from "./parts";

function Actuals({ items }: { items: BeforeAfterQuote[] }) {
  return (
    <section className="bf-section" aria-labelledby="bf-actuals">
      <div className="bf-h2row">
        <ActualBadge />
        <h2 id="bf-actuals" className="bf-h2">
          Described as possible last year, described as having happened this year
        </h2>
      </div>
      {items.map((a) => (
        <div key={`${a.ticker}-${a.changeId}`} className="bf-pair">
          <EvidenceHead name={a.name} sub={a.shortTitle} />
          <BeforeAfter old={a.old} now={a.new} isFixture={a.isFixture} />
        </div>
      ))}
    </section>
  );
}

function Figures({ items }: { items: BeforeAfterQuote[] }) {
  return (
    <section className="bf-section" aria-labelledby="bf-figures">
      <h2 id="bf-figures" className="bf-h2">
        Figures that were not in last year&apos;s filing
      </h2>
      {items.map((f) => {
        const label = f.figureChanged ? "Figure changed" : "New figure";
        return (
          <div key={`${f.ticker}-${f.changeId}-${f.detail ?? ""}`} className="bf-pair">
            <EvidenceHead
              name={f.name}
              sub={f.detail ? `${label}: ${detailLabel(f.detail)}` : label}
              link={f.figureChanged ? null : <QuoteLink quote={f.new} isFixture={f.isFixture} />}
            />
            {f.figureChanged ? (
              <BeforeAfter old={f.old} now={f.new} isFixture={f.isFixture} />
            ) : f.new ? (
              <FilingQuote quote={f.new} side="new" />
            ) : null}
          </div>
        );
      })}
    </section>
  );
}

function RiskList({ items, omitted }: { items: RiskListItem[]; omitted: number }) {
  if (items.length === 0) return <p className="bf-secondary">None in this selection.</p>;
  return (
    <>
      <ul className="bf-risklist">
        {items.map((r) => (
          <li key={`${r.ticker}-${r.changeId}`}>
            <span className="bf-strong">{r.name}</span> {r.shortTitle}
            {r.note ? <span className="bf-secondary"> ({r.note})</span> : null}
          </li>
        ))}
      </ul>
      {omitted > 0 ? <p className="bf-secondary">+{fmt(omitted)} more in the library</p> : null}
    </>
  );
}

function NewAndDropped({ model }: { model: BriefingModel }) {
  return (
    <section className="bf-section bf-grid2 bf-keep" aria-label="New and dropped risk factors">
      <div>
        <div className="bf-h3row">
          <Pill tone={CHANGE_TONE.new}>New risk</Pill>
          <h3 className="bf-h3">Not in last year&apos;s filing</h3>
        </div>
        <RiskList items={model.newRisks} omitted={model.newRisksOmitted} />
      </div>
      <div>
        <div className="bf-h3row">
          <Pill tone={CHANGE_TONE.removed}>Dropped risk</Pill>
          <h3 className="bf-h3">In last year&apos;s filing, not this year&apos;s</h3>
        </div>
        <RiskList items={model.droppedRisks} omitted={model.droppedRisksOmitted} />
      </div>
      <p className="bf-quiet bf-span2">
        Dropped can mean moved. A dropped heading can be language folded into another risk factor. Confirm in the filing before
        reading anything into it.
      </p>
    </section>
  );
}

function QuietStrip({ q }: { q: QuietCompany }) {
  if (q.changed === 0 || q.items.length === 0) {
    return (
      <p className="bf-strip">
        <span className="bf-strong">{q.name}</span> changed nothing meaningful ({fmt(q.changed)} of {fmt(q.total)}).
      </p>
    );
  }
  return (
    <p className="bf-strip">
      <span className="bf-strong">{q.name}&apos;s</span> {fmt(q.changed)} {q.changed === 1 ? "change" : "changes"}, for completeness:{" "}
      {q.items.map((i) => i.shortTitle).join("; ")}
    </p>
  );
}

export function EvidencePage({ model }: { model: BriefingModel }) {
  const empty =
    model.actuals.length === 0 &&
    model.figures.length === 0 &&
    model.newRisks.length === 0 &&
    model.droppedRisks.length === 0 &&
    model.quiet.length === 0;
  return (
    <BriefingPage n={3} label="What became real, what appeared, what disappeared">
      {model.actuals.length > 0 ? <Actuals items={model.actuals} /> : null}
      {model.figures.length > 0 ? <Figures items={model.figures} /> : null}
      {empty ? (
        <p className="bf-secondary">No risk factor in this selection moved from possible to actual, added a figure, appeared or dropped.</p>
      ) : (
        <NewAndDropped model={model} />
      )}
      {model.quiet.length > 0 ? (
        <section className="bf-section" aria-label="Quiet companies">
          {model.quiet.map((q) => (
            <QuietStrip key={q.ticker} q={q} />
          ))}
        </section>
      ) : null}
    </BriefingPage>
  );
}
