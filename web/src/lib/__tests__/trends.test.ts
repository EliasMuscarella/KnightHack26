import assert from "node:assert/strict";
import { test } from "node:test";

import { buildHeatmap, cellIntensity, cellTone, headlineTopic, rankTopics, relativeTime, sourceLine } from "../trends.ts";

const topic = (name: string, companies: string[], sentences: number, source: "lexicon" | "entity" | "phrase" = "lexicon") => ({
  topic: name,
  source,
  company_count: companies.length,
  sentence_count: sentences,
  companies,
  examples: companies.map((t) => ({ ticker: t, change_id: "a".repeat(16), sentence_id: "x:1:1", short_title: "t", status: "added" as const, text: "s", added_spans: [[0, 1]] as [number, number][], matched_terms: [name] })),
});

test("topics rank by company count, then sentences, then name; phrases need two companies", () => {
  const { shared, single } = rankTopics([topic("Tariffs", ["A", "B", "C"], 4), topic("China", ["A", "B"], 9), topic("Taiwan", ["A", "B"], 9), topic("Solo", ["A"], 2), topic("some phrase", ["B"], 1, "phrase")]);
  assert.deepEqual(shared.map((t) => t.topic), ["Tariffs", "China", "Taiwan"]);
  assert.deepEqual(single.map((t) => t.topic), ["Solo"]);
});

test("heatmap caps columns at ten plus Other and sorts rows by activity", () => {
  const activity = [];
  for (let i = 0; i < 12; i++) activity.push({ ticker: "AAA", category: `cat_${i}`, risk_factors: 1, change_ids: ["c"], added_sentences: 12 - i, removed_sentences: 0, modified_sentences: 0, added_words: 10, removed_words: 0, modified_words: 0, max_score: 10 });
  activity.push({ ticker: "BBB", category: "cat_0", risk_factors: 2, change_ids: ["d", "e"], added_sentences: 1, removed_sentences: 30, modified_sentences: 2, added_words: 5, removed_words: 300, modified_words: 20, max_score: 40 });
  const hm = buildHeatmap(activity, [{ ticker: "CCC", name: "C", analysis_id: "", old_fiscal_year: 2024, new_fiscal_year: 2025, total_changes: 0, meaningful_changes: 0, by_change_type: {} }]);
  assert.equal(hm.columns.length, 11);
  assert.equal(hm.columns[10], "other");
  assert.deepEqual(hm.rows.map((r) => r.ticker), ["AAA", "BBB", "CCC"]); // AAA 78 sentences, BBB 33, CCC none
  const bbb = hm.rows[1].cells.get("cat_0")!;
  assert.equal(cellTone(bbb), "less");
  assert.equal(cellTone(hm.rows[0].cells.get("cat_0")), "more");
  assert.equal(cellTone(undefined), "empty");
  assert.ok(cellIntensity(bbb, hm.maxActivity) > 0.15 && cellIntensity(bbb, hm.maxActivity) <= 1);
  assert.equal(cellIntensity(undefined, hm.maxActivity), 0);
});

test("the headline names a most widespread topic only when two or more companies share it", () => {
  assert.equal(headlineTopic({ topic: "Tariffs", company_count: 1 }), null);
  assert.deepEqual(headlineTopic({ topic: "Tariffs", company_count: 3 }), { topic: "Tariffs", company_count: 3 });
  assert.equal(headlineTopic(null), null);
});

test("source line and relative time", () => {
  const now = new Date("2026-10-11T12:00:00Z");
  assert.equal(relativeTime("2026-10-11T11:58:00Z", now), "2 min ago");
  assert.equal(relativeTime("2026-10-11T09:00:00Z", now), "3 hours ago");
  assert.equal(relativeTime(null, now), null);
  assert.equal(sourceLine({ source: "databricks", computed_at: "2026-10-11T11:58:00Z" }, now), "Computed in Databricks, updated 2 min ago");
  assert.equal(sourceLine({ source: "local", computed_at: null }, now), "Source: the local report library");
});
