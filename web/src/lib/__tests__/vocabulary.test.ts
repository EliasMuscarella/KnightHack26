import assert from "node:assert/strict";
import { test } from "node:test";

import { changeLevel, countedLabel, directionOf, displayTitle, levelSegments, shortTitleFromHeading } from "../vocabulary.ts";

test("short titles cut at the first clause and never end in a function word", () => {
  assert.equal(
    shortTitleFromHeading("Failure to meet the evolving needs of our industry and markets may adversely impact our financial results."),
    "Failure to meet the evolving needs of our industry and markets",
  );
  assert.equal(shortTitleFromHeading("Commercial arrangements expose us to counterparty risks."), "Commercial arrangements expose us to counterparty risks");
  const long = shortTitleFromHeading("The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K.");
  assert.ok(long.endsWith("…") && long.split(" ").length <= 13);
  assert.ok(!/\s(and|or|the|of|to)$/.test(long.replace("…", "")));
});

test("displayTitle uses a real short title and falls back from truncations", () => {
  assert.equal(displayTitle("Export controls on China sales", "We are subject to complex laws…"), "Export controls on China sales");
  assert.equal(displayTitle("We are subject to complex laws, rules…", "We are subject to complex laws, rules, regulations, and political actions."), "We are subject to complex laws");
  assert.equal(displayTitle("We are subject to complex laws, rules…", null), "We are subject to complex laws");
});

test("counted labels pluralize nouns only", () => {
  assert.equal(countedLabel(2, "new"), "2 new risks");
  assert.equal(countedLabel(1, "materially_reworded"), "1 major update");
  assert.equal(countedLabel(5, "materially_reworded"), "5 major updates");
  assert.equal(countedLabel(3, "expanded"), "3 expanded");
});

test("direction and level mapping", () => {
  assert.equal(directionOf("new"), "more");
  assert.equal(directionOf("reduced"), "less");
  assert.equal(directionOf("materially_reworded"), "rewrite");
  assert.equal(directionOf("largely_unchanged"), "none");
  assert.deepEqual([changeLevel(60), changeLevel(25), changeLevel(24)], ["High", "Medium", "Low"]);
  assert.deepEqual([levelSegments(100), levelSegments(40), levelSegments(0)], [3, 2, 1]);
});
