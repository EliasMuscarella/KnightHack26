import assert from "node:assert/strict";
import { test } from "node:test";

import { alnumKey, hasWordChars, neutralizeCaseOnly, neutralizeRangePair, pairDisplaySpans, sliceSpans, wordRanges } from "../diffDisplay.ts";

type Op = "equal" | "insert" | "delete";
const sp = (op: Op, text: string) => ({ op, text });
const joined = (spans: { text: string }[]) => spans.map((s) => s.text).join("");
const changed = (spans: { op: string; text: string }[]) => spans.filter((s) => s.op !== "equal").map((s) => s.text.trim());

test("spans without letters or digits are not word changes", () => {
  assert.equal(hasWordChars(", "), false);
  assert.equal(hasWordChars(" — ; "), false);
  assert.equal(hasWordChars("U.S."), true);
  assert.equal(hasWordChars("2025"), true);
  assert.equal(alnumKey("The,"), "the");
  assert.equal(alnumKey("data-center"), alnumKey("Data Center"));
  assert.deepEqual(wordRanges("a, b", [[1, 2], [3, 4]]), [[3, 4]]);
});

test("case-only edits across a pair are drawn plain on both sides; real edits keep their marks", () => {
  const oldSpans = [sp("delete", "The"), sp("equal", " company sells "), sp("delete", "chips"), sp("equal", ".")];
  const newSpans = [sp("insert", "the"), sp("equal", " company sells "), sp("insert", "systems"), sp("equal", ".")];
  const out = neutralizeCaseOnly(oldSpans, newSpans);
  assert.equal(joined(out.old), joined(oldSpans));
  assert.equal(joined(out.new), joined(newSpans));
  assert.deepEqual(changed(out.old), ["chips"]);
  assert.deepEqual(changed(out.new), ["systems"]);
  // inputs untouched
  assert.equal(oldSpans[0].op, "delete");
});

test("punctuation and spacing differences inside a merged run also match", () => {
  const oldSpans = [sp("equal", "Under "), sp("delete", "export"), sp("equal", " "), sp("delete", "controls,"), sp("equal", " we")];
  const newSpans = [sp("equal", "Under "), sp("insert", "Export"), sp("equal", " "), sp("insert", "Controls"), sp("equal", " we")];
  const out = neutralizeCaseOnly(oldSpans, newSpans);
  assert.deepEqual(changed(out.old), []);
  assert.deepEqual(changed(out.new), []);
  const merged = neutralizeCaseOnly([sp("delete", "data center")], [sp("insert", "Data-Center")]);
  assert.deepEqual(changed(merged.new), []);
  assert.deepEqual(neutralizeCaseOnly(undefined, null), { old: [], new: [] });
});

test("pairDisplaySpans neutralizes modified pairs only", () => {
  const sentences = [
    { id: "o:1", side: "old", status: "modified", counterpart_id: "n:1", text: "The x.", diff_spans: [sp("delete", "The"), sp("equal", " x.")] },
    { id: "n:1", side: "new", status: "modified", counterpart_id: "o:1", text: "the x.", diff_spans: [sp("insert", "the"), sp("equal", " x.")] },
    { id: "n:2", side: "new", status: "added", counterpart_id: null, text: "New.", diff_spans: null },
  ];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const m = pairDisplaySpans(sentences as any);
  assert.deepEqual(changed(m.get("o:1")!), []);
  assert.deepEqual(changed(m.get("n:1")!), []);
  assert.equal(m.get("n:2"), null);
});

test("character-range pairs drop case-only and punctuation-only ranges", () => {
  const oldText = "Export controls may affect sales; the rules may change.";
  const newText = "export controls have affected sales, and the rules changed.";
  const out = neutralizeRangePair(oldText, [[0, 6], [16, 19], [32, 33]], newText, [[0, 6], [16, 29], [35, 36]]);
  assert.deepEqual(out.old, [[16, 19]]);
  assert.deepEqual(out.new, [[16, 29]]);
  assert.deepEqual(neutralizeRangePair(null, undefined, undefined, null), { old: [], new: [] });
});

test("sliceSpans cuts an exact window without altering text", () => {
  const spans = [sp("equal", "abc "), sp("insert", "def"), sp("equal", " ghi")];
  const cut = sliceSpans(spans, 2, 9);
  assert.equal(joined(cut), "abc def ghi".slice(2, 9));
  assert.deepEqual(cut.map((s) => s.op), ["equal", "insert", "equal"]);
});
