import assert from "node:assert/strict";
import { test } from "node:test";

import { pickHero } from "../hero.ts";

function comp(ticker: string, scores: Record<string, number>, highlights: { change_id: string; kind: string }[], is_fixture = false) {
  return {
    is_fixture,
    company: { ticker, name: ticker, cik: "0000000000" },
    changes: Object.entries(scores).map(([id, score]) => ({ id, score })),
    highlights: highlights.map((h) => ({ ...h, old_sentence_id: null, new_sentence_id: `${h.change_id}:1`, short_title: "t", detail: null })),
  } as unknown as Parameters<typeof pickHero>[0][number];
}

test("prefers Potential became actual, then score, then ticker, then position", () => {
  const a = comp("ZZZ", { c1: 90 }, [{ change_id: "c1", kind: "potential_became_actual" }]);
  const b = comp("AAA", { c2: 90, c3: 100 }, [
    { change_id: "c3", kind: "new_figure" },
    { change_id: "c2", kind: "potential_became_actual" },
  ]);
  const pick = pickHero([a, b]);
  assert.ok(pick);
  assert.equal(pick.comparison.company.ticker, "AAA"); // tie on score 90 -> ticker
  assert.equal(pick.change.id, "c2");
  // input order does not matter
  assert.equal(pickHero([b, a])?.change.id, "c2");
});

test("falls back to any highlight and never uses fixture data", () => {
  const fx = comp("FIXTUR", { c1: 100 }, [{ change_id: "c1", kind: "potential_became_actual" }], true);
  const plain = comp("ABC", { c9: 10 }, [{ change_id: "c9", kind: "new_risk" }]);
  assert.equal(pickHero([fx, plain])?.change.id, "c9");
  assert.equal(pickHero([fx]), null);
  assert.equal(pickHero([]), null);
});
