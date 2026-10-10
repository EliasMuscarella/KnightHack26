import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { actualSnippets, markedRanges, snippet, snippetWindow, termOccurrences, topicEvidence, type Range } from "../snippet.ts";

interface Vector {
  name: string;
  text: string;
  evidence: Range[];
  max: number;
  start: number;
  end: number;
}

const vectors = JSON.parse(readFileSync(new URL("../../../../tests/fixtures/snippet_vectors.json", import.meta.url), "utf-8")) as { cases: Vector[] };

test("snippetWindow matches the Python reference on every parity vector", () => {
  assert.ok(vectors.cases.length > 0);
  for (const v of vectors.cases) {
    const w = snippetWindow(v.text, v.evidence, v.max);
    assert.deepEqual([w.start, w.end], [v.start, v.end], v.name);
  }
});

test("the window always contains the earliest evidence span and stays within budget", () => {
  const words = Array.from({ length: 120 }, (_, i) => `word${i}`).join(" ");
  for (let a = 0; a < words.length - 30; a += 37) {
    const b = a + 25;
    const w = snippetWindow(words, [[a, b]], 220);
    assert.ok(w.start <= a && b <= w.end, `span ${a}-${b} in ${w.start}-${w.end}`);
    assert.ok(w.end - w.start <= 220 + 25);
  }
});

test("snippet never throws on missing evidence or text", () => {
  assert.deepEqual(snippet(undefined, undefined, 220), { start: 0, end: 0, leading: false, trailing: false });
  const long = "x ".repeat(300);
  const s = snippet(long, undefined, 220);
  assert.equal(s.start, 0);
  assert.ok(s.trailing && !s.leading);
});

test("marked ranges trim whitespace, merge adjacent runs and cover whole added sentences", () => {
  const s = {
    text: "We sell chips and boards to cloud providers.",
    status: "modified",
    diff_spans: [
      { op: "equal", text: "We sell chips " },
      { op: "insert", text: "and" },
      { op: "insert", text: " boards " },
      { op: "equal", text: "to cloud providers." },
    ],
  };
  assert.deepEqual(markedRanges(s, "insert"), [[14, 24]]);
  assert.deepEqual(markedRanges(s, "delete"), []);
  assert.deepEqual(markedRanges({ text: "All new.", status: "added", diff_spans: null }, "insert"), [[0, 8]]);
  assert.deepEqual(markedRanges({ text: "All gone.", status: "removed" }, "delete"), [[0, 9]]);
});

test("topic evidence prefers the term inside the added spans, whole word and hyphen tolerant", () => {
  const text = "We collect data. Under the Gramm-Leach-Bliley Act and data-protection laws, we must notify clients.";
  const at = text.indexOf("Gramm");
  const added: Range[] = [[at - 10, text.length]];
  const ev = topicEvidence(text, ["Gramm-Leach-Bliley Act"], added);
  assert.deepEqual(ev, [[at, at + "Gramm-Leach-Bliley Act".length]]);
  assert.equal(termOccurrences("data protection laws", text).length, 1);
  assert.equal(termOccurrences("data", "database metadata").length, 0);
  // no occurrence inside the added spans: fall back to the spans
  assert.deepEqual(topicEvidence(text, ["clients"], [[0, 4]]), [[0, 4]]);
  // a long sentence: the displayed window contains the term
  const long = `${"In providing services to clients, we collect, use, store, and transmit sensitive information. ".repeat(4)}We are subject to the Gramm-Leach-Bliley Act.`;
  const i = long.indexOf("Gramm");
  const w = snippetWindow(long, topicEvidence(long, ["Gramm-Leach-Bliley Act"], [[i - 7, long.length]]), 320);
  assert.ok(long.slice(w.start, w.end).includes("Gramm-Leach-Bliley Act"));
});

test("potential-to-actual windows survive rows without span fields and contain the marked words", () => {
  const oldText = `${"Our business could be affected by export controls in several regions where we sell. ".repeat(4)}We may be subject to new licensing requirements.`;
  const newText = `${"Our business was affected by export controls in several regions where we sell. ".repeat(4)}We became subject to new licensing requirements.`;
  // A payload row from an older API: no old_spans / new_spans at all.
  const legacy = { old_text: oldText, new_text: newText } as { old_text: string; new_text: string; old_spans?: Range[]; new_spans?: Range[] };
  const w = actualSnippets(legacy, 220);
  assert.ok(w.old && w.new);
  assert.equal(w.old.start, 0);
  assert.ok(w.old.trailing && !w.old.leading);
  // undefined and null span fields behave the same
  assert.deepEqual(actualSnippets({ old_text: oldText, new_text: newText, old_spans: undefined, new_spans: null }, 220), w);
  assert.deepEqual(actualSnippets({ old_text: null, new_text: undefined }, 220), { old: null, new: null });
  // with spans: the window contains them, ellipses on both trimmed sides
  const at = newText.indexOf("became");
  const v = actualSnippets({ old_text: oldText, new_text: newText, old_spans: [], new_spans: [[at, at + 6]] }, 220);
  assert.ok(v.new && v.new.start <= at && at + 6 <= v.new.end);
  assert.ok(v.new.leading);
});
