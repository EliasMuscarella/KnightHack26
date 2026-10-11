import assert from "node:assert/strict";
import { test } from "node:test";

import { acceptRemote, createLimiter, createRemoteMemo, mergeComparisons, remoteRefs, type RemoteRef } from "../remoteComparisons.ts";
import { pickSpecimens } from "../specimen.ts";

type Any = any; // eslint-disable-line @typescript-eslint/no-explicit-any

const ID = (n: number) => n.toString(16).padStart(16, "0");

/** A comparison with one "new risk" highlight, enough for looksLike/merge/pickSpecimens. */
function comp(ticker: string, opts: { id?: string; fixture?: boolean; tag?: string; score?: number } = {}): Any {
  const sid = `${ticker}:n:1`;
  return {
    analysis_id: opts.id ?? ID(1),
    is_fixture: opts.fixture === true,
    company: { ticker, name: `${ticker} CORP` },
    old_filing: { fiscal_year: 2024 },
    new_filing: { fiscal_year: 2025 },
    summary: {},
    sentence_index: { [sid]: { text: `Sentence ${ticker} ${opts.tag ?? ""}.` } },
    changes: [
      {
        id: "c1",
        score: opts.score ?? 50,
        short_title: `Title ${ticker} ${opts.tag ?? ""}`,
        title: `Heading ${ticker}`,
        sentences: [{ id: sid, text: `Sentence ${ticker} ${opts.tag ?? ""}.`, status: "added", diff_spans: null, alignment_similarity: null }],
      },
    ],
    highlights: [{ kind: "new_risk", change_id: "c1", old_sentence_id: null, new_sentence_id: sid, detail: null }],
  };
}

// Same check as looksLikeComparison in api.ts (which this module receives by injection).
const validate = (x: unknown): x is Any => {
  const c = x as Any;
  return !!c && typeof c.analysis_id === "string" && typeof c.company?.ticker === "string" && Array.isArray(c.changes) && !!c.sentence_index;
};

const ref = (ticker: string, id: string | null = ID(1)): RemoteRef => ({ ticker, analysisId: id });

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
}

const tick = () => new Promise((r) => setImmediate(r));

test("remoteRefs: valid tickers only, no fixtures, no local tickers, first card per ticker, sorted, capped", () => {
  const cards = [
    { ticker: "STT", analysis_id: ID(2) },
    { ticker: "ABBV", analysis_id: "not-hex" },
    { ticker: "AAPL", analysis_id: ID(3) }, // local
    { ticker: "BAC", analysis_id: ID(4) },
    { ticker: "BAC", analysis_id: ID(5) }, // duplicate: first wins
    { ticker: "FIXTUR", is_fixture: true },
    { ticker: "../etc", analysis_id: ID(6) },
    { ticker: "abc" },
    { ticker: 42 },
    null,
  ];
  assert.deepEqual(remoteRefs(cards, new Set(["AAPL"])), [
    { ticker: "ABBV", analysisId: null },
    { ticker: "BAC", analysisId: ID(4) },
    { ticker: "STT", analysisId: ID(2) },
  ]);
  assert.deepEqual(remoteRefs(cards, new Set(["AAPL"]), 2).map((r) => r.ticker), ["ABBV", "BAC"]);
});

test("acceptRemote: keeps only a non-fixture comparison of the requested ticker and analysis", () => {
  assert.ok(acceptRemote(ref("BAC"), comp("BAC"), validate));
  assert.equal(acceptRemote(ref("BAC"), comp("CAT"), validate), null);
  assert.equal(acceptRemote(ref("BAC"), comp("BAC", { fixture: true }), validate), null);
  assert.equal(acceptRemote(ref("BAC", ID(9)), comp("BAC"), validate), null);
  assert.ok(acceptRemote(ref("BAC", null), comp("BAC", { id: ID(9) }), validate));
  assert.equal(acceptRemote(ref("BAC"), { company: { ticker: "BAC" } }, validate), null);
  assert.equal(acceptRemote(ref("BAC"), null, validate), null);
});

test("mergeComparisons: local wins, one per ticker, fixtures dropped, order independent", () => {
  const local = [comp("NVDA", { tag: "local" }), comp("AAPL", { tag: "local" })];
  const remote = [comp("STT"), comp("NVDA", { tag: "remote" }), comp("STT", { tag: "dup" }), comp("FIX", { fixture: true }), comp("BAC")];
  const merged = mergeComparisons(local, remote);
  assert.deepEqual(merged.map((c) => c.company.ticker), ["AAPL", "BAC", "NVDA", "STT"]);
  assert.match(merged[2].changes[0].short_title, /local/);
  assert.doesNotMatch(merged[3].changes[0].short_title, /dup/);
  // Same reports in, same slides out, whatever order the API answered in.
  const a = pickSpecimens(mergeComparisons(local, [comp("STT"), comp("BAC", { score: 80 })]));
  const b = pickSpecimens(mergeComparisons([...local].reverse(), [comp("BAC", { score: 80 }), comp("STT")]));
  assert.deepEqual(a, b);
  assert.equal(a[0].ticker, "BAC");
});

test("limiter: never more than n tasks at once", async () => {
  const run = createLimiter(4);
  let active = 0;
  let peak = 0;
  const gates = Array.from({ length: 10 }, () => deferred<void>());
  const all = gates.map((g, i) =>
    run(async () => {
      active++;
      peak = Math.max(peak, active);
      await g.promise;
      active--;
      return i;
    }),
  );
  await tick();
  assert.equal(active, 4);
  gates.forEach((g) => g.resolve());
  assert.deepEqual(await Promise.all(all), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.equal(peak, 4);
});

test("memo: concurrent callers share one fetch per ticker; a warm call does not refetch", async () => {
  const calls: string[] = [];
  const memo = createRemoteMemo({ fetcher: async (t) => (calls.push(t), comp(t)), validate });
  const refs = [ref("BAC"), ref("STT")];
  const [a, b] = await Promise.all([memo.get(refs, 1000), memo.get(refs, 1000)]);
  assert.deepEqual(calls.sort(), ["BAC", "STT"]);
  assert.deepEqual(a.map((c) => c.company.ticker), ["BAC", "STT"]);
  assert.deepEqual(b.map((c) => c.company.ticker), ["BAC", "STT"]);
  await memo.get(refs, 1000);
  assert.equal(calls.length, 2);
});

test("memo: bounded wait returns partial results; the fetch keeps going and fills the memo", async () => {
  const slow = deferred<unknown>();
  let calls = 0;
  const memo = createRemoteMemo({
    fetcher: (t) => {
      calls++;
      return t === "STT" ? slow.promise : Promise.resolve(comp(t));
    },
    validate,
  });
  const refs = [ref("BAC"), ref("STT")];
  const started = Date.now();
  const first = await memo.get(refs, 30);
  assert.ok(Date.now() - started < 1000);
  assert.deepEqual(first.map((c) => c.company.ticker), ["BAC"]);
  assert.equal(memo.inFlight(), 1);
  slow.resolve(comp("STT"));
  await tick();
  const second = await memo.get(refs, 0);
  assert.deepEqual(second.map((c) => c.company.ticker), ["BAC", "STT"]);
  assert.equal(calls, 2);
});

test("memo: during a slow cold fill only the first bounded wait blocks", async () => {
  let t = 0;
  const slow = deferred<unknown>();
  const memo = createRemoteMemo({ fetcher: () => slow.promise, validate, now: () => t });
  const refs = [ref("BAC")];
  let started = Date.now();
  assert.deepEqual(await memo.get(refs, 60), []);
  assert.ok(Date.now() - started >= 50);
  t = 60; // the fetch was requested 60 ms ago: its wait is used up
  started = Date.now();
  assert.deepEqual(await memo.get(refs, 60), []);
  assert.ok(Date.now() - started < 1000);
  t = 30; // a caller inside the window waits only for what is left of it
  started = Date.now();
  await memo.get(refs, 60);
  assert.ok(Date.now() - started < 1000);
  slow.resolve(comp("BAC"));
  await tick();
  assert.equal((await memo.get(refs, 0)).length, 1);
});

test("memo: TTL expiry refreshes in the background while serving the last good comparison", async () => {
  let t = 0;
  let version = 0;
  const gate = deferred<void>();
  const memo = createRemoteMemo({
    fetcher: async (tk) => {
      version++;
      if (version > 1) await gate.promise;
      return comp(tk, { tag: `v${version}` });
    },
    validate,
    ttlMs: 1000,
    now: () => t,
  });
  const refs = [ref("BAC")];
  assert.match((await memo.get(refs, 1000))[0].changes[0].short_title, /v1/);
  t = 999;
  await memo.get(refs, 1000);
  assert.equal(version, 1);
  t = 1000; // expired: the stale value is returned at once, a refresh starts
  const stale = await memo.get(refs, 5000);
  assert.match(stale[0].changes[0].short_title, /v1/);
  assert.equal(version, 2);
  gate.resolve();
  await tick();
  await tick();
  assert.match((await memo.get(refs, 0))[0].changes[0].short_title, /v2/);
});

test("memo: failures are dropped and retried only after retryMs; bad payloads count as failures", async () => {
  let t = 0;
  let calls = 0;
  const memo = createRemoteMemo({
    fetcher: async (tk) => {
      calls++;
      if (calls === 1) throw new Error("down");
      if (calls === 2) return comp("OTHER");
      return comp(tk);
    },
    validate,
    retryMs: 100,
    now: () => t,
  });
  const refs = [ref("BAC")];
  assert.deepEqual(await memo.get(refs, 1000), []);
  t = 50;
  assert.deepEqual(await memo.get(refs, 1000), []);
  assert.equal(calls, 1);
  t = 100;
  assert.deepEqual(await memo.get(refs, 1000), []); // wrong ticker in the payload
  t = 200;
  assert.equal((await memo.get(refs, 1000)).length, 1);
  assert.equal(calls, 3);
});

test("memo: a new analysis id for a ticker never shows the old report; delisted tickers are dropped", async () => {
  const calls: string[] = [];
  const memo = createRemoteMemo({
    fetcher: async (tk) => {
      calls.push(tk);
      return comp(tk, { id: calls.length === 1 ? ID(1) : ID(2) });
    },
    validate,
  });
  assert.equal((await memo.get([ref("BAC", ID(1))], 1000))[0].analysis_id, ID(1));
  const next = await memo.get([ref("BAC", ID(2))], 1000);
  assert.equal(next[0].analysis_id, ID(2));
  assert.deepEqual(await memo.get([ref("CAT")], 0), []); // BAC no longer listed: not returned
  assert.deepEqual(calls, ["BAC", "BAC", "CAT"]);
});

test("memo: at most `concurrency` fetches in flight", async () => {
  let active = 0;
  let peak = 0;
  const memo = createRemoteMemo({
    fetcher: async (tk) => {
      active++;
      peak = Math.max(peak, active);
      await new Promise((r) => setTimeout(r, 5));
      active--;
      return comp(tk);
    },
    validate,
    concurrency: 4,
  });
  const refs = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"].map((t) => ref(t));
  assert.equal((await memo.get(refs, 5000)).length, 10);
  assert.equal(peak, 4);
});
