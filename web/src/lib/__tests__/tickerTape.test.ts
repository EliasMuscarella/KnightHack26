import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatTapeChange,
  formatTapePrice,
  formatTapeTime,
  parseTickerTape,
  tapeDirection,
  tapeDurationSeconds,
  tapeVisible,
} from "../tickerTape.ts";

const q = (over: Record<string, unknown> = {}) => ({
  symbol: "ABC",
  name: "Example",
  price: 10,
  change: 0.5,
  change_pct: 5,
  updated_at: "2026-10-09T20:02:00Z",
  ...over,
});

test("rejects bodies that are not a tape payload", () => {
  assert.equal(parseTickerTape(null), null);
  assert.equal(parseTickerTape("ok"), null);
  assert.equal(parseTickerTape({ status: "great", quotes: [] }), null);
});

test("drops malformed quotes and keeps the rest", () => {
  const p = parseTickerTape({
    status: "ok",
    source: "Finnhub",
    as_of: "2026-10-09T20:02:00Z",
    quotes: [
      q(),
      q({ symbol: "abc" }),
      q({ symbol: "TOOLONGX" }),
      q({ symbol: "<b>" }),
      q({ symbol: "NAN", price: Number.NaN }),
      q({ symbol: "NEG", price: -1 }),
      q({ symbol: "STR", price: "12.00" }),
      q({ symbol: "INF", change: Number.POSITIVE_INFINITY }),
      q({ symbol: "PCT", change_pct: "1%" }),
      q({ symbol: "NUL", change: null, change_pct: null, name: 42, updated_at: "yesterday" }),
      q(), // duplicate symbol
      "nope",
    ],
  });
  assert.ok(p);
  assert.deepEqual(
    p.quotes.map((x) => x.symbol),
    ["ABC", "NUL"],
  );
  const nul = p.quotes[1];
  assert.equal(nul.name, "NUL");
  assert.equal(nul.change, null);
  assert.equal(nul.updated_at, null);
  assert.equal(p.as_of, "2026-10-09T20:02:00Z");
});

test("bad as_of and source fall back safely", () => {
  const p = parseTickerTape({ status: "stale", source: "<script>", as_of: "not a time", quotes: [q()] });
  assert.ok(p);
  assert.equal(p.source, "Finnhub");
  assert.equal(p.as_of, null);
});

test("the tape shows only with quotes and a usable status", () => {
  assert.equal(tapeVisible(null), false);
  assert.equal(tapeVisible(parseTickerTape({ status: "unavailable", quotes: [q()] })), false);
  assert.equal(tapeVisible(parseTickerTape({ status: "ok", quotes: [] })), false);
  assert.equal(tapeVisible(parseTickerTape({ status: "ok", quotes: [q()] })), true);
  assert.equal(tapeVisible(parseTickerTape({ status: "stale", quotes: [q()] })), true);
});

test("direction follows the day change; rounding to zero is flat", () => {
  assert.equal(tapeDirection({ change: 1.05, change_pct: 0.58 }), "up");
  assert.equal(tapeDirection({ change: -1.05, change_pct: -0.58 }), "down");
  assert.equal(tapeDirection({ change: 0, change_pct: 0 }), "flat");
  assert.equal(tapeDirection({ change: -0.001, change_pct: -0.0001 }), "flat");
  assert.equal(tapeDirection({ change: null, change_pct: -0.4 }), "down");
  assert.equal(tapeDirection({ change: null, change_pct: null }), "flat");
});

test("formats prices and changes with two decimals and an explicit sign", () => {
  assert.equal(formatTapePrice(1234.5), "1,234.50");
  assert.equal(formatTapeChange({ change: 1.05, change_pct: 0.58 }), "+1.05 (+0.58%)");
  assert.equal(formatTapeChange({ change: -12.3, change_pct: -1.234 }), "−12.30 (−1.23%)");
  assert.equal(formatTapeChange({ change: -0.001, change_pct: 0 }), "0.00 (0.00%)");
  assert.equal(formatTapeChange({ change: 2, change_pct: null }), "+2.00");
  assert.equal(formatTapeChange({ change: null, change_pct: 1.5 }), "+1.50%");
  assert.equal(formatTapeChange({ change: null, change_pct: null }), null);
});

test("times render in Eastern time with plain spaces", () => {
  assert.equal(formatTapeTime("2026-10-09T20:02:00Z"), "4:02 PM ET");
  assert.equal(formatTapeTime("2026-10-09T20:02:00Z", true), "Oct 9, 4:02 PM ET");
  assert.equal(formatTapeTime("2026-01-15T14:30:00Z", true), "Jan 15, 9:30 AM ET");
  assert.equal(formatTapeTime(null), null);
  assert.equal(formatTapeTime("garbage"), null);
});

test("animation length scales with the number of quotes", () => {
  assert.equal(tapeDurationSeconds(50), 125);
  assert.equal(tapeDurationSeconds(2), 20);
});
