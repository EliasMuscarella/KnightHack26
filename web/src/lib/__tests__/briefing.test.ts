import "./briefingResolve.ts";

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const { buildBriefing, briefingId, fiscalYearNote, hedgeSupport, UNTITLED_RISK } = await import("../briefing/build.ts");
const { filterTrends, topicLabel } = await import("../briefing/trendsFilter.ts");
const { spansFromOffsets } = await import("../briefing/quotes.ts");
const { buildQuestions } = await import("../briefing/questions.ts");
const { cmpFigure } = await import("../briefing/order.ts");

type Input = Parameters<typeof buildBriefing>[0];
type Comparison = Input["comparisons"][number];
type Trends = NonNullable<Input["trends"]>;

// Synthetic dev-only comparison (every string prefixed FIXTURE:).
const FIXTURE: Comparison = JSON.parse(readFileSync(new URL("../../../../contract/fixtures/FIXTURE_comparison.json", import.meta.url), "utf8"));

/** A copy of the fixture under another ticker, optionally reshaped. */
function comp(ticker: string, opts: { scoreShift?: number; allUnchanged?: boolean; periodEnd?: string; extraNew?: number; highlights?: Comparison["highlights"] } = {}): Comparison {
  const c: Comparison = JSON.parse(JSON.stringify(FIXTURE));
  c.company = { ...c.company, ticker, name: `${ticker} HOLDINGS INC` };
  c.analysis_id = `${ticker.toLowerCase()}-analysis`;
  for (const ch of c.changes) ch.score += opts.scoreShift ?? 0;
  if (opts.allUnchanged) {
    for (const ch of c.changes) ch.change_type = "largely_unchanged";
    c.highlights = [];
  }
  for (let i = 0; i < (opts.extraNew ?? 0); i++) {
    const base = c.changes.find((x) => x.change_type === "new")!;
    c.changes.push({ ...JSON.parse(JSON.stringify(base)), id: `extra${String(i).padStart(11, "0")}`, score: 10 + i });
  }
  if (opts.highlights) c.highlights = opts.highlights;
  const by: Record<string, number> = { new: 0, removed: 0, expanded: 0, reduced: 0, materially_reworded: 0, largely_unchanged: 0 };
  for (const ch of c.changes) by[ch.change_type]++;
  c.summary = { ...c.summary, by_change_type: by, total_changes: c.changes.length };
  if (opts.periodEnd) c.new_filing = { ...c.new_filing, period_of_report: opts.periodEnd };
  return c;
}

const ADDED_ID = "0000000000-25-000001:5:3"; // an added sentence in change 530f7128dc266e93
const ADDED_TEXT = FIXTURE.sentence_index[ADDED_ID].text;

function example(ticker: string, change_id = "530f7128dc266e93", sentence_id = ADDED_ID) {
  return { ticker, change_id, sentence_id, short_title: "FIXTURE: t", status: "added" as const, text: FIXTURE.sentence_index[sentence_id].text, added_spans: [[9, 20]] as [number, number][], matched_terms: ["tariffs"] };
}

function topic(name: string, companies: string[], sentences: number, source: "lexicon" | "entity" | "phrase" = "lexicon") {
  return { topic: name, source, company_count: companies.length, sentence_count: sentences, companies, examples: companies.map((t) => example(t)) };
}

function trends(topics: ReturnType<typeof topic>[], tickers: string[]): Trends {
  return {
    status: "ok",
    source: "local",
    computed_at: "2026-10-01T00:00:00Z",
    companies: tickers.map((t) => ({ ticker: t, name: `${t} HOLDINGS INC`, analysis_id: `${t.toLowerCase()}-analysis`, old_fiscal_year: 2024, new_fiscal_year: 2025, total_changes: 7, meaningful_changes: 6, by_change_type: {} })),
    headline: { companies: tickers.length, meaningful_changes: 0, top_topic: null },
    topics,
    category_activity: tickers.map((t) => ({ ticker: t, category: "regulation", risk_factors: 1, change_ids: ["c"], added_sentences: 1, removed_sentences: 0, modified_sentences: 0, added_words: 5, removed_words: 0, modified_words: 0, max_score: 10 })),
    potential_to_actual: [],
    change_mix: tickers.map((t) => ({ ticker: t, by_change_type: {} })),
  };
}

function input(comparisons: Comparison[], t: Trends | null, missingTickers: string[] = []): Input {
  return { comparisons, trends: t, title: "Disclosure Briefing", preparedFor: null, generatedAt: "2026-10-11T00:00:00Z", missingTickers };
}

test("trends post-filter recounts topics for the selection before ranking", () => {
  const t = trends([topic("Tariffs", ["AAA", "BBB", "ZZZ"], 9), topic("China", ["AAA", "ZZZ"], 4), topic("Taiwan", ["AAA", "BBB"], 3)], ["AAA", "BBB", "ZZZ"]);
  const f = filterTrends(t, new Map([["AAA", "aaa-analysis"], ["BBB", "bbb-analysis"]]));
  assert.deepEqual(f.topics.map((x) => [x.topic, x.company_count, x.sentence_count, x.partialCount]), [
    ["Taiwan", 2, 3, false], // complete: library count kept
    ["Tariffs", 2, 2, true], // ZZZ dropped: examples kept
  ]); // China has one selected company and is dropped
  assert.ok(f.topics.every((x) => x.examples.every((e) => e.ticker !== "ZZZ")));
  assert.deepEqual(f.category_activity.map((r) => r.ticker), ["AAA", "BBB"]);
  assert.deepEqual(f.change_mix.map((r) => r.ticker), ["AAA", "BBB"]);
  // One company: topics need one hit.
  assert.deepEqual(filterTrends(t, new Map([["AAA", "aaa-analysis"]])).topics.map((x) => x.topic), ["China", "Taiwan", "Tariffs"]);
  // A ticker whose trends rows come from another report is excluded and reported.
  const stale = filterTrends(t, new Map([["AAA", "aaa-analysis"], ["BBB", "other"]]));
  assert.deepEqual(stale.staleTickers, ["BBB"]);
  assert.deepEqual(stale.topics, []);
  assert.deepEqual(filterTrends(null, new Map()).topics, []);
});

test("topic labels are sentence case", () => {
  assert.equal(topicLabel("increased cost", "phrase"), "Increased cost");
  assert.equal(topicLabel("ai technology", "phrase"), "AI technology");
  assert.equal(topicLabel("AI regulation", "lexicon"), "AI regulation");
});

test("offsets become equal/insert spans that rebuild the text", () => {
  const text = "Tariffs increased our costs this year.";
  const spans = spansFromOffsets(text, [[22, 27], [0, 7], [5, 9], [100, 120]])!;
  assert.deepEqual(spans, [
    { op: "insert", text: "Tariffs i" },
    { op: "equal", text: "ncreased our " },
    { op: "insert", text: "costs" },
    { op: "equal", text: " this year." },
  ]);
  assert.equal(spans.map((s) => s.text).join(""), text);
  assert.equal(spansFromOffsets(text, []), null);
  assert.deepEqual(spansFromOffsets(text, [[0, text.length]]), [{ op: "insert", text }]);
});

test("figures order dollars, then percentages, then counts, larger first", () => {
  const xs = ["15%", "1,000", "$750 million -> $1.0 billion", "$4.5 billion", null, "52.7%"];
  assert.deepEqual([...xs].sort(cmpFigure), ["$4.5 billion", "$750 million -> $1.0 billion", "52.7%", "15%", "1,000", null]);
});

test("read first: actuals, figures, spreading topics, quiet, in that order", () => {
  const fig = (amount: string, id: string) => ({ change_id: "6f1bd4f571f61777", kind: "new_figure" as const, detail: amount, old_sentence_id: null, new_sentence_id: id, short_title: "FIXTURE: t" });
  const a = comp("AAA", { highlights: [...FIXTURE.highlights!, fig("$2 billion", "0000000000-25-000001:1:1")] });
  const b = comp("BBB", { scoreShift: 5, highlights: [...FIXTURE.highlights!, fig("$9 million", "0000000000-25-000001:1:2")] });
  const q = comp("QQQ", { allUnchanged: true });
  const t = trends([topic("Tariffs", ["AAA", "BBB"], 4), topic("Export controls", ["AAA", "BBB", "QQQ"], 2), topic("Solo", ["AAA"], 9)], ["AAA", "BBB", "QQQ"]);
  const m = buildBriefing(input([a, b, q], t));
  // Actual scores: BBB d434 58, BBB 530f 54, AAA d434 53, AAA 530f 49. With a quiet company the
  // first three kinds leave one slot, so only the top spreading topic (3 companies) fits.
  assert.deepEqual(
    m.readFirst.map((r) => [r.kind, r.tickers.join("+"), r.changeId, r.pageRef]),
    [
      ["potential_became_actual", "BBB", "d434664e80f07fbb", 3],
      ["potential_became_actual", "BBB", "530f7128dc266e93", 3],
      ["new_figure", "AAA", "6f1bd4f571f61777", 3], // $2 billion before $9 million
      ["new_figure", "BBB", "6f1bd4f571f61777", 3],
      ["spreading", "AAA+BBB+QQQ", null, 2],
      ["quiet", "QQQ", null, null],
    ],
  );
  const spread = m.readFirst[4];
  assert.match(spread.lead, /^Export controls: new language at 3 of 3 companies$/);
  assert.equal(m.readFirst[5].lead, `${m.companies[2].name} changed nothing meaningful (0 of 7)`);
  // Validated claims are used only when the interpretation ran; the fixture's 530f... did not.
  assert.equal(m.readFirst[1].supportSource, "data");
  assert.equal(m.readFirst[1].support, hedgeSupport("FIXTURE: could increase -> have increased"));
  assert.equal(m.readFirst[0].supportSource, "validated_claim");
  assert.equal(m.readFirst[0].support, b.changes.find((c) => c.id === "d434664e80f07fbb")!.interpretation.claims![0].text);
  assert.equal(m.headline.newFigures.count, 2);
  assert.deepEqual(m.headline.newFigures.examples, ["$2 billion", "$9 million"]);
});

test("read first fills with new risks when fewer than four items were found", () => {
  const c = comp("AAA", { highlights: [] });
  const m = buildBriefing(input([c], null));
  assert.deepEqual(m.readFirst.map((r) => [r.kind, r.changeId]), [
    ["new_risk", "a7ab944f05ff339d"],
    ["removed_risk", "99545bba86c20d17"],
  ]);
  assert.equal(hedgeSupport("may -> experienced"), "Last year: 'may'. This year: 'experienced'.");
});

test("single company: themes from its own topics, no matrix, no spreading item", () => {
  const t = trends([topic("Tariffs", ["AAA", "BBB"], 4)], ["AAA", "BBB"]);
  const m = buildBriefing(input([comp("AAA")], t));
  assert.equal(m.themes.length, 1);
  const th = m.themes[0];
  assert.deepEqual([th.companyCount, th.sentenceCount, th.tickers], [1, 1, ["AAA"]]);
  const q = th.quotes[0];
  assert.equal(q.quote.text, ADDED_TEXT);
  assert.equal(q.quote.sentenceId, ADDED_ID);
  assert.deepEqual(q.quote.spans, spansFromOffsets(ADDED_TEXT, [[9, 20]]));
  assert.equal(q.changeType, "expanded");
  assert.equal(q.edgarUrl, FIXTURE.new_filing.edgar_url);
  assert.equal(m.matrix, null);
  assert.ok(!m.readFirst.some((r) => r.kind === "spreading"));
});

test("themes: one quote per company, at most four, the rest named; matrix rows by hits", () => {
  const tickers = ["AAA", "BBB", "CCC", "DDD", "EEE"];
  const cs = tickers.map((t, i) => comp(t, { scoreShift: i }));
  const t = trends([topic("Tariffs", tickers, 12), topic("China", ["AAA", "BBB"], 3), topic("Gone", ["AAA", "BBB"], 2)], tickers);
  t.topics[2].examples = t.topics[2].examples.map((e) => ({ ...e, sentence_id: "nope:1:1" })); // not in the index: no quote
  const m = buildBriefing(input(cs, t));
  const th = m.themes[0];
  assert.equal(th.topic, "Tariffs");
  assert.deepEqual(th.quotes.map((q) => q.ticker), ["EEE", "DDD", "CCC", "BBB"]); // parent change score desc
  assert.equal(th.alsoNamed.length, 1);
  assert.deepEqual(m.themes[1].quotes.length, 2);
  assert.ok(m.matrix);
  assert.deepEqual(m.matrix!.topics.map((x) => x.topic), ["Tariffs", "China", "Gone"]);
  assert.deepEqual(m.matrix!.rows.slice(0, 2).map((r) => r.hits), [[true, true, true], [true, true, true]]);
  assert.deepEqual(m.matrix!.rows[4].hits, [true, false, false]);
});

test("same input gives a deep-equal model; the id ignores order and generatedAt", () => {
  const t = trends([topic("Tariffs", ["AAA", "BBB"], 4)], ["AAA", "BBB"]);
  const i1 = input([comp("AAA"), comp("BBB", { scoreShift: 3 })], t);
  const m1 = buildBriefing(i1);
  const m2 = buildBriefing(JSON.parse(JSON.stringify(i1)));
  assert.deepEqual(m1, m2);
  assert.equal(briefingId(["b", "a"]), briefingId(["a", "b"]));
  const m3 = buildBriefing({ ...i1, generatedAt: "2030-01-01T00:00:00Z" });
  assert.equal(m3.briefingId, m1.briefingId);
});

test("missing tickers, fixture data and an omitted page 2 are noted", () => {
  const m = buildBriefing(input([comp("AAA"), comp("BBB")], trends([], ["AAA", "BBB"]), ["XYZ"]));
  assert.deepEqual(m.missingTickers, ["XYZ"]);
  assert.ok(m.notes.includes("Not in the library: XYZ."));
  assert.ok(m.notes.includes("No shared topics among these companies, so page 2 is omitted."));
  assert.ok(m.notes.some((n) => n.includes("FIXTURE")));
  assert.equal(m.hasFixture, true);
  assert.deepEqual(m.themes, []);
  assert.equal(m.matrix, null);
});

test("quiet companies: none changed, or at most five and at most 15%", () => {
  const big = comp("BIG", { extraNew: 40 }); // 46 meaningful of 47: not quiet
  const zero = comp("ZERO", { allUnchanged: true });
  const few = comp("FEW", { allUnchanged: true });
  // 3 meaningful of 25 (12%): quiet.
  for (let i = 0; i < 18; i++) few.changes.push({ ...JSON.parse(JSON.stringify(few.changes[0])), id: `pad${String(i).padStart(13, "0")}` });
  for (const ch of few.changes.slice(0, 3)) ch.change_type = "expanded";
  few.summary.by_change_type = { new: 0, removed: 0, expanded: 3, reduced: 0, materially_reworded: 0, largely_unchanged: few.changes.length - 3 };
  const m = buildBriefing(input([big, few, zero], null));
  assert.deepEqual(m.quiet.map((q) => [q.ticker, q.changed, q.total, q.items.length]), [
    ["ZERO", 0, 7, 0],
    ["FEW", 3, 25, 3],
  ]);
  // Read first lists only companies at or under 10%.
  const quiet = m.readFirst.find((r) => r.kind === "quiet")!;
  assert.deepEqual(quiet.tickers, ["ZERO"]);
});

test("risk lists cap at twelve and count the rest; notes name a new party", () => {
  const c = comp("AAA", { extraNew: 14 });
  const m = buildBriefing(input([c], null));
  assert.equal(m.newRisks.length, 12);
  assert.equal(m.newRisksOmitted, 3);
  assert.equal(m.newRisks[0].changeId, "a7ab944f05ff339d"); // score 34 beats the extras (10..23)
  assert.equal(m.droppedRisks.length, 1);
  assert.equal(m.droppedRisksOmitted, 0);
  const q = buildBriefing(input([comp("AAA")], null)).quiet;
  assert.deepEqual(q, []);
  const named = comp("BBB");
  named.highlights = [{ change_id: "a7ab944f05ff339d", kind: "new_named_party", detail: "FIXTURE: Westland", old_sentence_id: null, new_sentence_id: "0000000000-25-000001:2:2", short_title: "x" }];
  assert.equal(buildBriefing(input([named], null)).newRisks[0].note, "names FIXTURE: Westland");
});

test("evidence quotes are verbatim sentence-index text with the diff's spans", async () => {
  const m = buildBriefing(input([comp("AAA"), comp("BBB")], null));
  assert.equal(m.actuals.length, 4);
  for (const a of m.actuals) {
    for (const q of [a.old, a.new]) {
      assert.ok(q && q.sentenceId);
      assert.equal(q.text, FIXTURE.sentence_index[q.sentenceId].text);
      if (q.spans) assert.equal(q.spans.map((s) => s.text).join(""), q.text);
    }
  }
  assert.ok(m.actuals[0].new!.spans!.some((s) => s.op === "insert"));
  // The fixture's old side only had words added around it: its spans are all "equal".
  assert.ok(m.actuals[0].old!.spans!.every((s) => s.op === "equal"));
  // A dropped risk's old sentence (status "removed") is one delete span.
  const removed = FIXTURE.changes.find((c) => c.change_type === "removed")!;
  const s = removed.sentences[0];
  const { quoteById } = await import("../briefing/quotes.ts");
  assert.deepEqual(quoteById(FIXTURE, removed, s.id), { sentenceId: s.id, text: s.text, spans: [{ op: "delete", text: s.text }] });
  assert.equal(quoteById(FIXTURE, removed, "missing:0:0"), null);
});

test("questions draw from each basis in order, at most two per basis first", () => {
  const ba = (id: string, kind: "potential_became_actual" | "new_figure", detail: string | null = null, figureChanged = false) => ({
    ticker: "AAA", name: "A", changeId: id, shortTitle: id, kind, detail, figureChanged, old: null, new: null, oldEdgarUrl: "", newEdgarUrl: "", isFixture: false,
  });
  const risk = (id: string) => ({ ticker: "AAA", name: "A", changeId: id, title: id, shortTitle: id, changeType: "new" as const, note: null });
  const qs = buildQuestions([ba("a1", "potential_became_actual"), ba("a2", "potential_became_actual"), ba("a3", "potential_became_actual")], [ba("f1", "new_figure", "$4.5 billion"), ba("a1", "new_figure", "$1 -> $2", true)], [risk("n1")], []);
  assert.deepEqual(qs.map((q) => [q.changeId, q.basis]), [
    ["a1", "potential became actual"],
    ["a2", "potential became actual"],
    ["a3", "potential became actual"],
    ["f1", "new figure"],
    ["n1", "new"],
  ]);
  assert.match(qs[3].question, /^How was the \$4\.5 billion figure determined/);
  for (const q of qs) assert.doesNotMatch(q.question, /riskier|probab|likely|buy|sell/i);
});

test("fiscal-year note only when a year does not end in December", () => {
  const base = buildBriefing(input([comp("AAA", { periodEnd: "2025-12-31" }), comp("BBB", { periodEnd: "2025-12-31" })], null));
  assert.equal(base.fiscalYearNote, null);
  const mixed = buildBriefing(input([comp("AAA", { periodEnd: "2026-01-25" }), comp("BBB", { periodEnd: "2025-12-31" })], null));
  assert.match(mixed.fiscalYearNote!, /^Fiscal years differ by company: .*FY2025 ended in January 2026, while 1 company reports on a calendar year\. 'This year' always means each company's most recent 10-K\.$/);
  assert.equal(fiscalYearNote([]), null);
});

test("a heading that is only the company name falls back to the section group", () => {
  const c = comp("AAA");
  const ch = c.changes.find((x) => x.change_type === "new")!;
  ch.title = c.company.name;
  ch.short_title = c.company.name;
  assert.equal(buildBriefing(input([c], null)).newRisks[0].shortTitle, ch.section_group);
  ch.section_group = null;
  assert.equal(buildBriefing(input([c], null)).newRisks[0].shortTitle, UNTITLED_RISK);
});
