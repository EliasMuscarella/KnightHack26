import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

// selection.ts imports "@/lib/ticker" and "./types" the way Next resolves them; map both to files
// here so Node's test runner can load the module unchanged.
const SRC = new URL("../../", import.meta.url);
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith("@/")) return next(new URL(`${specifier.slice(2)}.ts`, SRC).href, context);
    if (specifier.startsWith(".") && !/\.[cm]?[jt]sx?$/.test(specifier) && context.parentURL?.startsWith(pathToFileURL(SRC.pathname).href)) {
      return next(`${specifier}.ts`, context);
    }
    return next(specifier, context);
  },
});

const { cleanText, DEFAULT_TITLE, MAX_PREPARED_FOR_CHARS, MAX_TITLE_CHARS, parseSelection, parseTickers, selectionQuery } = await import("../briefing/selection.ts");
const { MAX_BRIEFING_COMPANIES } = await import("../briefing/types.ts");

test("tickers are uppercased, split on commas and spaces, and de-duplicated in order", () => {
  const sel = parseSelection({ tickers: " nvda, aapl  msft,NVDA ,, brk.b" });
  assert.deepEqual(sel.tickers, ["NVDA", "AAPL", "MSFT", "BRK.B"]);
  assert.deepEqual(sel.rejected, []);
  assert.equal(sel.truncated, false);
});

test("repeated tickers params are merged", () => {
  assert.deepEqual(parseSelection({ tickers: ["nvda", "AMD,nvda"] }).tickers, ["NVDA", "AMD"]);
});

test("invalid entries are rejected, never kept", () => {
  const sel = parseSelection({ tickers: "NVDA,BAD!!,TOOLONGX,<script>,A1" });
  assert.deepEqual(sel.tickers, ["NVDA"]);
  assert.deepEqual(sel.rejected, ["BAD!!", "TOOLONGX", "<SCRIPT>", "A1"]);
  // At most five rejected entries are reported, each at most 12 characters.
  const many = parseSelection({ tickers: "1,2,3,4,5,6,7,ABCDEFGHIJKLMNOP" });
  assert.equal(many.rejected.length, 5);
  assert.ok(parseSelection({ tickers: "ABCDEFGHIJKLMNOP" }).rejected.every((r) => r.length <= 12));
});

test("no tickers, empty params and null params give an empty selection with defaults", () => {
  for (const p of [null, undefined, {}, { tickers: "" }, { tickers: " , " }]) {
    const sel = parseSelection(p);
    assert.deepEqual(sel.tickers, []);
    assert.equal(sel.title, DEFAULT_TITLE);
    assert.equal(sel.preparedFor, null);
  }
});

test("the count is capped at MAX_BRIEFING_COMPANIES with truncated set", () => {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
  assert.ok(letters.length > MAX_BRIEFING_COMPANIES, "the test needs more distinct tickers than the cap");
  const sel = parseTickers(letters.slice(0, MAX_BRIEFING_COMPANIES + 1).join(","));
  assert.equal(sel.tickers.length, MAX_BRIEFING_COMPANIES);
  assert.equal(sel.truncated, true);
  assert.deepEqual(sel.tickers, letters.slice(0, MAX_BRIEFING_COMPANIES));
  const exact = parseTickers(letters.slice(0, MAX_BRIEFING_COMPANIES).join(","));
  assert.equal(exact.truncated, false);
});

test("title and prepared-for are trimmed, whitespace collapsed, length capped", () => {
  const sel = parseSelection({ tickers: "NVDA", title: "  Q3   review  ", for: "  Investment\tcommittee " });
  assert.equal(sel.title, "Q3 review");
  assert.equal(sel.preparedFor, "Investment committee");
  const long = parseSelection({ tickers: "NVDA", title: "x".repeat(200), for: "y".repeat(200) });
  assert.equal(long.title.length, MAX_TITLE_CHARS);
  assert.equal(long.preparedFor?.length, MAX_PREPARED_FOR_CHARS);
  assert.equal(parseSelection({ tickers: "NVDA", title: "   " }).title, DEFAULT_TITLE);
  assert.equal(parseSelection({ tickers: "NVDA", for: "   " }).preparedFor, null);
  assert.equal(parseSelection({ tickers: "NVDA", title: ["First", "Second"] }).title, "First");
});

test("control characters are stripped from free text", () => {
  const sel = parseSelection({ tickers: "NVDA", title: "Board\u0000 brief\u0007ing\r\nnotes\u007f", for: "\u001bAlice" });
  assert.equal(sel.title, "Board brief ing notes");
  assert.equal(sel.preparedFor, "Alice");
  assert.equal(cleanText("a\u0008b", 10), "a b");
  // A cut at the cap never leaves trailing whitespace.
  assert.equal(cleanText("abcd efgh", 5), "abcd");
});

test("selectionQuery rebuilds the query from validated values and round-trips", () => {
  const sel = parseSelection({ tickers: "nvda, aapl ,BAD!!", title: " My  brief ", for: "Committee & co" });
  const q = selectionQuery(sel);
  assert.equal(q, "tickers=NVDA%2CAAPL&title=My+brief&for=Committee+%26+co");
  assert.ok(!q.includes("BAD"));
  const back = parseSelection(Object.fromEntries(new URLSearchParams(q)));
  assert.deepEqual(back.tickers, sel.tickers);
  assert.equal(back.title, sel.title);
  assert.equal(back.preparedFor, sel.preparedFor);
  assert.deepEqual(back.rejected, []);
});

test("selectionQuery omits the default title and an empty prepared-for", () => {
  assert.equal(selectionQuery({ tickers: ["NVDA"], title: DEFAULT_TITLE, preparedFor: null }), "tickers=NVDA");
  const back = parseSelection(Object.fromEntries(new URLSearchParams(selectionQuery(parseSelection({ tickers: "AMD" })))));
  assert.equal(back.title, DEFAULT_TITLE);
  assert.equal(back.preparedFor, null);
});
