import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_SIDE_CHARS, pickSpecimens, SPECIMEN_KINDS } from "../specimen.ts";

type Hl = { kind: string; change_id: string; old?: string; new?: string; detail?: string };

function comp(ticker: string, hls: Hl[], opts: { fixture?: boolean; texts?: Record<string, string>; score?: number; sim?: number } = {}) {
  const ids = [...new Set(hls.map((h) => h.change_id))];
  const index: Record<string, { text: string }> = {};
  for (const h of hls) {
    for (const sid of [h.old, h.new]) if (sid) index[sid] = { text: opts.texts?.[sid] ?? `Sentence ${sid}.` };
  }
  return {
    is_fixture: opts.fixture === true,
    company: { ticker, name: `${ticker} CORP` },
    old_filing: { fiscal_year: 2024 },
    new_filing: { fiscal_year: 2025 },
    changes: ids.map((id) => ({
      id,
      score: opts.score ?? 50,
      short_title: `Title ${id}`,
      title: `Heading ${id}`,
      sentences: hls
        .filter((h) => h.change_id === id)
        .flatMap((h) => [h.old, h.new])
        .filter((x): x is string => !!x)
        .map((sid) => ({ id: sid, text: opts.texts?.[sid] ?? `Sentence ${sid}.`, status: "modified", diff_spans: null, alignment_similarity: opts.sim ?? 0.9 })),
    })),
    highlights: hls.map((h) => ({ kind: h.kind, change_id: h.change_id, old_sentence_id: h.old ?? null, new_sentence_id: h.new ?? null, detail: h.detail ?? null })),
    sentence_index: index,
  } as never;
}

test("one slide per kind, in the fixed kind order, never the same risk factor twice", () => {
  const a = comp("AAA", [
    { kind: "new_risk", change_id: "c1", new: "n1" },
    { kind: "potential_became_actual", change_id: "c2", old: "o2", new: "n2" },
    { kind: "removed_risk", change_id: "c3", old: "o3" },
    { kind: "new_figure", change_id: "c2", new: "n9", detail: "$1" },
  ]);
  const kinds = pickSpecimens([a]).map((s) => s.kind);
  assert.deepEqual(kinds, ["potential_became_actual", "new_risk", "removed_risk"]);
  assert.ok(kinds.every((k, i) => i === 0 || SPECIMEN_KINDS.indexOf(k as never) > SPECIMEN_KINDS.indexOf(kinds[i - 1] as never)));
});

test("a company that already has a slide is passed over while another company has a candidate", () => {
  const a = comp("AAA", [
    { kind: "potential_became_actual", change_id: "a1", old: "ao", new: "an" },
    { kind: "new_risk", change_id: "a2", new: "a2n" },
  ], { score: 90 });
  const b = comp("BBB", [{ kind: "new_risk", change_id: "b1", new: "b1n" }], { score: 10 });
  const out = pickSpecimens([a, b]);
  assert.deepEqual(out.map((s) => `${s.kind}:${s.ticker}`), ["potential_became_actual:AAA", "new_risk:BBB"]);
});

test("falls back to a used company when it is the only one with that kind", () => {
  const a = comp("AAA", [
    { kind: "potential_became_actual", change_id: "a1", old: "ao", new: "an" },
    { kind: "new_risk", change_id: "a2", new: "a2n" },
  ]);
  assert.deepEqual(pickSpecimens([a]).map((s) => s.kind), ["potential_became_actual", "new_risk"]);
});

test("fixtures and over-long sentences are never used; figureChanged needs both sides", () => {
  const fx = comp("FIX", [{ kind: "new_risk", change_id: "f1", new: "f1n" }], { fixture: true });
  const long = comp("LNG", [{ kind: "new_risk", change_id: "l1", new: "l1n" }], { texts: { l1n: "x".repeat(MAX_SIDE_CHARS + 1) } });
  assert.deepEqual(pickSpecimens([fx, long]), []);
  const fig = comp("FIG", [
    { kind: "new_figure", change_id: "g1", new: "g1n", detail: "$4.5 billion" },
    { kind: "new_figure", change_id: "g2", old: "g2o", new: "g2n", detail: "$1.4 billion -> $2.6 billion" },
  ], { score: 50 });
  const picked = pickSpecimens([fig]);
  assert.equal(picked.length, 1);
  assert.equal(picked[0].figureChanged, picked[0].old !== null);
});

test("deterministic: input order does not change the result", () => {
  const a = comp("AAA", [{ kind: "new_risk", change_id: "a1", new: "a1n" }], { score: 40 });
  const b = comp("BBB", [{ kind: "new_risk", change_id: "b1", new: "b1n" }], { score: 40 });
  assert.deepEqual(pickSpecimens([a, b]), pickSpecimens([b, a]));
  assert.equal(pickSpecimens([a, b])[0].ticker, "AAA");
});

test("a before/after pair must be one edited sentence: loose alignments are skipped", () => {
  const hl = [{ kind: "potential_became_actual", change_id: "p1", old: "po", new: "pn" }];
  assert.equal(pickSpecimens([comp("AAA", hl, { sim: 0.5 })]).length, 0);
  assert.equal(pickSpecimens([comp("AAA", hl, { sim: 0.7 })]).length, 1);
  // one-sided highlights have no pair to align
  assert.equal(pickSpecimens([comp("AAA", [{ kind: "new_risk", change_id: "n1", new: "nn" }], { sim: 0.1 })]).length, 1);
});
