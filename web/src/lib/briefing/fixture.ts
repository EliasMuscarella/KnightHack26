/**
 * FIXTURE briefing model for design work on the briefing document. Hand-made: every company,
 * sentence, figure and identifier is invented, and every free-text string starts with "FIXTURE "
 * so it can never pass as real data (numbers, tickers, dates and structural labels excepted).
 *
 * Rendered only by /briefing/print?fixture=1 when RISKDIFF_SHOW_FIXTURE=1 (lib/data.ts
 * `fixtureEnabled`). Never published, never part of a real briefing.
 */
import type { ChangeType, DiffSpan } from "@/types/comparison";

import {
  BRIEFING_TEMPLATE_VERSION,
  type AuditRow,
  type BeforeAfterQuote,
  type BriefingCompany,
  type BriefingModel,
  type CoverageRow,
  type MarkedQuote,
  type RiskListItem,
} from "./types";

/** "+word" = inserted, "-word" = deleted, anything else = unchanged; text is the parts joined. */
function mq(id: string, parts: string[]): MarkedQuote {
  const spans: DiffSpan[] = parts.map((p) =>
    p.startsWith("+") ? { op: "insert", text: p.slice(1) } : p.startsWith("-") ? { op: "delete", text: p.slice(1) } : { op: "equal", text: p },
  );
  return { sentenceId: id, text: spans.map((s) => s.text).join(""), spans };
}

/** A whole sentence new this year (no spans: the highlighter covers it). */
function whole(id: string, text: string): MarkedQuote {
  return { sentenceId: id, text, spans: null };
}

type Mix = Record<ChangeType, number>;

interface Seed {
  ticker: string;
  name: string;
  oldFY: number;
  newFY: number;
  periodEnd: string;
  filed: string;
  mix: Mix;
  wordsLast: number;
  wordsThis: number;
}

const SEEDS: Seed[] = [
  { ticker: "FXAA", name: "FIXTURE Alder", oldFY: 2025, newFY: 2026, periodEnd: "2026-01-25", filed: "2026-02-25", mix: { new: 4, expanded: 9, materially_reworded: 6, reduced: 2, removed: 3, largely_unchanged: 21 }, wordsLast: 12341, wordsThis: 12580 },
  { ticker: "FXBB", name: "FIXTURE Birch", oldFY: 2024, newFY: 2025, periodEnd: "2025-09-27", filed: "2025-10-31", mix: { new: 2, expanded: 5, materially_reworded: 3, reduced: 1, removed: 1, largely_unchanged: 24 }, wordsLast: 9874, wordsThis: 10112 },
  { ticker: "FXCC", name: "FIXTURE Cedar", oldFY: 2024, newFY: 2025, periodEnd: "2025-12-31", filed: "2026-02-06", mix: { new: 3, expanded: 7, materially_reworded: 4, reduced: 3, removed: 2, largely_unchanged: 30 }, wordsLast: 15020, wordsThis: 15433 },
  { ticker: "FXDD", name: "FIXTURE Dogwood", oldFY: 2025, newFY: 2026, periodEnd: "2026-01-31", filed: "2026-03-10", mix: { new: 2, expanded: 6, materially_reworded: 5, reduced: 2, removed: 1, largely_unchanged: 19 }, wordsLast: 11205, wordsThis: 11690 },
  { ticker: "FXEE", name: "FIXTURE Elm", oldFY: 2024, newFY: 2025, periodEnd: "2025-12-31", filed: "2026-01-29", mix: { new: 1, expanded: 4, materially_reworded: 7, reduced: 4, removed: 2, largely_unchanged: 16 }, wordsLast: 13402, wordsThis: 12755 },
  { ticker: "FXFF", name: "FIXTURE Fir", oldFY: 2024, newFY: 2025, periodEnd: "2025-12-31", filed: "2026-02-04", mix: { new: 1, expanded: 3, materially_reworded: 2, reduced: 1, removed: 0, largely_unchanged: 28 }, wordsLast: 8920, wordsThis: 9013 },
  { ticker: "FXGG", name: "FIXTURE Ginkgo", oldFY: 2025, newFY: 2026, periodEnd: "2026-03-31", filed: "2026-05-20", mix: { new: 0, expanded: 1, materially_reworded: 1, reduced: 0, removed: 0, largely_unchanged: 31 }, wordsLast: 10450, wordsThis: 10478 },
  { ticker: "FXHH", name: "FIXTURE Hazel", oldFY: 2024, newFY: 2025, periodEnd: "2025-12-31", filed: "2026-02-18", mix: { new: 0, expanded: 0, materially_reworded: 0, reduced: 0, removed: 0, largely_unchanged: 24 }, wordsLast: 7611, wordsThis: 7611 },
];

function total(m: Mix): number {
  return Object.values(m).reduce((s, n) => s + n, 0);
}

const companies: BriefingCompany[] = SEEDS.map((s, i) => {
  const t = total(s.mix);
  return {
    ticker: s.ticker,
    name: s.name,
    officialName: `${s.name.toUpperCase()} INC`,
    analysisId: `FIXTURE ${String(i + 1).padStart(2, "0")}a7c3e9f1b20d4c58`,
    oldFiscalYear: s.oldFY,
    newFiscalYear: s.newFY,
    oldPeriodEnd: s.periodEnd.replace(String(s.newFY), String(s.oldFY)),
    newPeriodEnd: s.periodEnd,
    newFilingDate: s.filed,
    newAccession: `FIXTURE 00000${i + 1}-${String(s.newFY).slice(2)}-0${i + 1}2`,
    oldAccession: `FIXTURE 00000${i + 1}-${String(s.oldFY).slice(2)}-0${i + 1}1`,
    newEdgarUrl: "FIXTURE no filing",
    oldEdgarUrl: "FIXTURE no filing",
    isFixture: true,
    totalRiskFactors: t,
    meaningfulChanges: t - s.mix.largely_unchanged,
    byChangeType: s.mix,
    newCount: s.mix.new,
    droppedCount: s.mix.removed,
    wordsThisYear: s.wordsThis,
    wordsLastYear: s.wordsLast,
    interpretationStatus: "ok",
  };
});

const byTicker = Object.fromEntries(companies.map((c) => [c.ticker, c]));
const nameOf = (t: string) => byTicker[t].name;

const coverage: CoverageRow[] = companies.map((c) => ({
  ticker: c.ticker,
  name: c.name,
  fyLabel: `FY${c.oldFiscalYear} → FY${c.newFiscalYear}`,
  changed: c.meaningfulChanges,
  total: c.totalRiskFactors,
  mix: c.byChangeType,
  newCount: c.newCount,
  droppedCount: c.droppedCount,
  wordsThisYear: c.wordsThisYear,
  wordsDelta: c.wordsThisYear - c.wordsLastYear,
}));

const audit: AuditRow[] = companies.map((c) => ({
  ticker: c.ticker,
  name: c.name,
  fyLabel: `FY${c.oldFiscalYear} → FY${c.newFiscalYear}`,
  latestFiled: c.newFilingDate,
  accession: c.newAccession,
  edgarUrl: c.newEdgarUrl,
  analysisId: c.analysisId,
  isFixture: true,
}));

function themeQuote(ticker: string, changeId: string, shortTitle: string, changeType: ChangeType, quote: MarkedQuote) {
  return { ticker, name: nameOf(ticker), changeId, shortTitle, changeType, quote, edgarUrl: "FIXTURE no filing", isFixture: true };
}

function ba(
  ticker: string,
  changeId: string,
  shortTitle: string,
  kind: BeforeAfterQuote["kind"],
  detail: string | null,
  figureChanged: boolean,
  old: MarkedQuote | null,
  now: MarkedQuote | null,
): BeforeAfterQuote {
  return { ticker, name: nameOf(ticker), changeId, shortTitle, kind, detail, figureChanged, old, new: now, oldEdgarUrl: "FIXTURE no filing", newEdgarUrl: "FIXTURE no filing", isFixture: true };
}

function risk(ticker: string, changeId: string, shortTitle: string, changeType: ChangeType, note: string | null = null): RiskListItem {
  return { ticker, name: nameOf(ticker), changeId, title: `${shortTitle}, as filed in full`, shortTitle, changeType, note };
}

const totals = companies.reduce(
  (s, c) => ({
    words: s.words + c.wordsThisYear,
    changed: s.changed + c.meaningfulChanges,
    total: s.total + c.totalRiskFactors,
    newCount: s.newCount + c.newCount,
    dropped: s.dropped + c.droppedCount,
  }),
  { words: 0, changed: 0, total: 0, newCount: 0, dropped: 0 },
);

export const FIXTURE_BRIEFING: BriefingModel = {
  templateVersion: BRIEFING_TEMPLATE_VERSION,
  briefingId: "FIXTURE 9c41e07d2b6a5f38e1c0d4a7b9e2f6c3",
  generatedAt: "2026-10-11T14:05:00Z",
  libraryAsOf: "2026-10-10T22:40:00Z",
  title: "FIXTURE Disclosure Briefing: chips and software",
  preparedFor: "FIXTURE Investment committee",
  companies,
  headline: {
    wordsThisYear: totals.words,
    readingHours: Math.round((totals.words / 250 / 60) * 10) / 10,
    changed: totals.changed,
    totalRiskFactors: totals.total,
    unchanged: totals.total - totals.changed,
    newCount: totals.newCount,
    droppedCount: totals.dropped,
    newFigures: { count: 3, examples: ["$4.5 billion", "about $800 million"] },
  },
  readFirst: [
    {
      kind: "potential_became_actual",
      lead: "FIXTURE Alder: export controls on accelerators.",
      support: "FIXTURE Last year's filing said new licensing rules could restrict sales; this year's says they did, with a charge taken.",
      supportSource: "validated_claim",
      tickers: ["FXAA"],
      changeId: "fx-aa-01",
      pageRef: 3,
    },
    {
      kind: "new_figure",
      lead: "FIXTURE Alder: inventory charge.",
      support: "FIXTURE The size of the charge appears for the first time.",
      supportSource: "data",
      tickers: ["FXAA"],
      changeId: "fx-aa-02",
      pageRef: 3,
    },
    {
      kind: "spreading",
      lead: "FIXTURE AI regulation: new language at 5 of 8 companies.",
      support: "FIXTURE Each one added wording on rules for AI models that was not in last year's risk factor.",
      supportSource: "data",
      tickers: ["FXAA", "FXBB", "FXCC", "FXDD", "FXEE"],
      changeId: null,
      pageRef: 2,
    },
    {
      kind: "new_risk",
      lead: "FIXTURE Cedar: data center power supply.",
      support: "FIXTURE Access to electricity for new capacity.",
      supportSource: "validated_claim",
      tickers: ["FXCC"],
      changeId: "fx-cc-01",
      pageRef: 3,
    },
    {
      kind: "removed_risk",
      lead: "FIXTURE Elm: dealer franchise litigation.",
      support: null,
      supportSource: null,
      tickers: ["FXEE"],
      changeId: "fx-ee-04",
      pageRef: 3,
    },
  ],
  coverage,
  themes: [
    {
      topic: "ai_regulation",
      label: "FIXTURE AI regulation",
      companyCount: 5,
      sentenceCount: 9,
      tickers: ["FXAA", "FXBB", "FXCC", "FXDD", "FXEE"],
      quotes: [
        themeQuote("FXAA", "fx-aa-03", "FIXTURE Laws governing AI models", "expanded", mq("fx-s1", ["FIXTURE Governments ", "+have adopted rules that require us to assess and document how our AI models are trained and deployed", ", and compliance may increase our costs."])),
        themeQuote("FXBB", "fx-bb-02", "FIXTURE Regulation of on-device AI features", "new", whole("fx-s2", "FIXTURE New rules for AI features in consumer devices could require us to change or withhold features in some countries.")),
        themeQuote("FXCC", "fx-cc-03", "FIXTURE AI services and customer data", "materially_reworded", mq("fx-s3", ["FIXTURE Our AI services ", "+are subject to the EU AI Act and similar laws", ", and any failure to comply could result in fines."])),
        themeQuote("FXDD", "fx-dd-02", "FIXTURE Use of AI in security products", "expanded", mq("fx-s4", ["FIXTURE We use AI in our products, ", "+and regulators have proposed audits of automated security decisions", "."])),
      ],
      alsoNamed: ["FIXTURE Elm"],
    },
    {
      topic: "tariffs",
      label: "FIXTURE Tariffs",
      companyCount: 3,
      sentenceCount: 4,
      tickers: ["FXBB", "FXEE", "FXFF"],
      quotes: [
        themeQuote("FXBB", "fx-bb-03", "FIXTURE Tariffs on imported components", "expanded", mq("fx-s5", ["FIXTURE ", "+Tariffs announced during the year increased the cost of components we import", ", and further changes could affect our margins."])),
        themeQuote("FXEE", "fx-ee-02", "FIXTURE Trade policy and vehicle pricing", "reduced", mq("fx-s6", ["FIXTURE ", "+New tariffs on imported parts", " may raise our vehicle costs."])),
      ],
      alsoNamed: ["FIXTURE Fir"],
    },
  ],
  matrix: {
    topics: [
      { topic: "ai_regulation", label: "FIXTURE AI regulation", companyCount: 5 },
      { topic: "tariffs", label: "FIXTURE Tariffs", companyCount: 3 },
      { topic: "export_controls", label: "FIXTURE Export controls", companyCount: 2 },
      { topic: "cybersecurity", label: "FIXTURE Cyber incidents", companyCount: 4 },
      { topic: "energy", label: "FIXTURE Energy supply", companyCount: 2 },
    ],
    rows: [
      { ticker: "FXAA", name: nameOf("FXAA"), hits: [true, false, true, true, true] },
      { ticker: "FXBB", name: nameOf("FXBB"), hits: [true, true, true, false, false] },
      { ticker: "FXCC", name: nameOf("FXCC"), hits: [true, false, false, true, true] },
      { ticker: "FXDD", name: nameOf("FXDD"), hits: [true, false, false, true, false] },
      { ticker: "FXEE", name: nameOf("FXEE"), hits: [true, true, false, false, false] },
      { ticker: "FXFF", name: nameOf("FXFF"), hits: [false, true, false, true, false] },
      { ticker: "FXGG", name: nameOf("FXGG"), hits: [false, false, false, false, false] },
      { ticker: "FXHH", name: nameOf("FXHH"), hits: [false, false, false, false, false] },
    ],
  },
  actuals: [
    ba(
      "FXAA",
      "fx-aa-01",
      "FIXTURE Export controls on accelerators",
      "potential_became_actual",
      "FIXTURE could -> were",
      false,
      mq("fx-o1", ["FIXTURE New licensing requirements ", "-could restrict", " our sales of accelerators to certain customers", "- and could require us to record charges", "."]),
      mq("fx-n1", ["FIXTURE New licensing requirements ", "+restricted", " our sales of accelerators to certain customers", "+, and we recorded a $4.5 billion charge for excess inventory", "."]),
    ),
    ba(
      "FXDD",
      "fx-dd-01",
      "FIXTURE Service outages",
      "potential_became_actual",
      "FIXTURE may -> experienced",
      false,
      mq("fx-o2", ["FIXTURE We ", "-may experience", " outages of our platform that ", "-could", " disrupt customers' operations."]),
      mq("fx-n2", ["FIXTURE We ", "+experienced a global outage in July", " of our platform that ", "+disrupted", " customers' operations", "+ and led to claims against us", "."]),
    ),
  ],
  figures: [
    ba("FXAA", "fx-aa-02", "FIXTURE Inventory and purchase commitments", "new_figure", "$4.5 billion", false, null, mq("fx-n3", ["FIXTURE We recorded charges of ", "+$4.5 billion", " related to excess inventory and purchase obligations."])),
    ba("FXCC", "fx-cc-02", "FIXTURE Capital expenditure commitments", "new_figure", "about $800 million", false, null, whole("fx-n4", "FIXTURE We have committed about $800 million to new data center leases that begin over the next two years.")),
    ba(
      "FXBB",
      "fx-bb-04",
      "FIXTURE Customer concentration",
      "new_figure",
      "22% -> 31%",
      true,
      mq("fx-o5", ["FIXTURE One customer accounted for ", "-22%", " of net revenue."]),
      mq("fx-n5", ["FIXTURE One customer accounted for ", "+31%", " of net revenue."]),
    ),
  ],
  newRisks: [
    risk("FXCC", "fx-cc-01", "FIXTURE Data center power supply", "new", "FIXTURE names a regional grid operator"),
    risk("FXAA", "fx-aa-04", "FIXTURE Competition from custom chips", "new", "FIXTURE names Groq"),
    risk("FXAA", "fx-aa-05", "FIXTURE Concentration in AI customers", "new"),
    risk("FXBB", "fx-bb-01", "FIXTURE Regulation of on-device AI features", "new"),
    risk("FXCC", "fx-cc-04", "FIXTURE Sovereign cloud requirements", "new"),
    risk("FXDD", "fx-dd-03", "FIXTURE Claims arising from the July outage", "new"),
    risk("FXEE", "fx-ee-01", "FIXTURE Battery material sourcing", "new"),
    risk("FXFF", "fx-ff-01", "FIXTURE Retail media business", "new"),
  ],
  newRisksOmitted: 5,
  droppedRisks: [
    risk("FXEE", "fx-ee-04", "FIXTURE Dealer franchise litigation", "removed"),
    risk("FXAA", "fx-aa-06", "FIXTURE Cryptocurrency mining demand", "removed"),
    risk("FXAA", "fx-aa-07", "FIXTURE Pending acquisition", "removed", "FIXTURE deal closed"),
    risk("FXAA", "fx-aa-08", "FIXTURE COVID-19 disruptions", "removed"),
    risk("FXBB", "fx-bb-05", "FIXTURE Legacy product transition", "removed"),
    risk("FXCC", "fx-cc-05", "FIXTURE LIBOR transition", "removed"),
    risk("FXCC", "fx-cc-06", "FIXTURE Office lease exposure", "removed"),
    risk("FXDD", "fx-dd-04", "FIXTURE Integration of an acquired company", "removed"),
    risk("FXEE", "fx-ee-05", "FIXTURE Semiconductor shortage", "removed"),
  ],
  droppedRisksOmitted: 3,
  quiet: [
    {
      ticker: "FXGG",
      name: nameOf("FXGG"),
      changed: 2,
      total: 33,
      items: [risk("FXGG", "fx-gg-01", "FIXTURE Release schedule of major titles", "expanded"), risk("FXGG", "fx-gg-02", "FIXTURE Platform store fees", "materially_reworded")],
    },
    { ticker: "FXHH", name: nameOf("FXHH"), changed: 0, total: 24, items: [] },
  ],
  questions: [
    { ticker: "FXAA", name: nameOf("FXAA"), changeId: "fx-aa-01", riskFactorTitle: "FIXTURE Export controls on accelerators", basis: "potential became actual", question: "FIXTURE Which customers and products do the new licensing requirements cover, and is the charge expected to recur?" },
    { ticker: "FXAA", name: nameOf("FXAA"), changeId: "fx-aa-02", riskFactorTitle: "FIXTURE Inventory and purchase commitments", basis: "new figure", question: "FIXTURE What portion of the $4.5 billion relates to purchase obligations that remain open?" },
    { ticker: "FXCC", name: nameOf("FXCC"), changeId: "fx-cc-01", riskFactorTitle: "FIXTURE Data center power supply", basis: "new", question: "FIXTURE What share of planned capacity depends on power agreements that are not yet signed?" },
    { ticker: "FXDD", name: nameOf("FXDD"), changeId: "fx-dd-01", riskFactorTitle: "FIXTURE Service outages", basis: "potential became actual", question: "FIXTURE What changes to release processes followed the July outage, and how many claims are pending?" },
    { ticker: "FXEE", name: nameOf("FXEE"), changeId: "fx-ee-04", riskFactorTitle: "FIXTURE Dealer franchise litigation", basis: "dropped", question: "FIXTURE Was the dealer litigation resolved, or is it now described under another risk factor?" },
  ],
  audit,
  fiscalYearNote:
    "FIXTURE Fiscal years differ by company: Alder's FY2026 ended in January 2026, Birch's FY2025 ended in September 2025, and the others end in December or March.",
  notes: [
    "FIXTURE Themes and the topic matrix are keyword matches over sentences added or changed this year.",
    "FIXTURE This briefing uses hand-made fixture data. No company, filing, sentence or figure in it is real.",
  ],
  hasFixture: true,
  missingTickers: [],
};
