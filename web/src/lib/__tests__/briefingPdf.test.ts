import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

// pdf.ts imports "@/lib/ticker" and "./selection" the way Next resolves them; map both to files here.
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

const { briefingFilename, DEFAULT_WEB_ORIGIN, FOOTER_TEMPLATE, printOrigin, printUrl } = await import("../briefing/pdf.ts");
const { parseSelection } = await import("../briefing/selection.ts");

test("the request origin is used only for localhost and 127.0.0.1", () => {
  assert.equal(printOrigin("http://localhost:3000/api/briefing.pdf?tickers=NVDA", undefined), "http://localhost:3000");
  assert.equal(printOrigin("http://127.0.0.1:3100/api/briefing.pdf", "https://riskdiff.example"), "http://127.0.0.1:3100");
  assert.equal(printOrigin("https://localhost/api/briefing.pdf", undefined), "https://localhost");
});

test("any other host falls back to RISKDIFF_WEB_ORIGIN, then the default", () => {
  assert.equal(printOrigin("http://evil.example/api/briefing.pdf", "https://riskdiff.example/some/path?x=1"), "https://riskdiff.example");
  assert.equal(printOrigin("http://evil.example/api/briefing.pdf", undefined), DEFAULT_WEB_ORIGIN);
  assert.equal(printOrigin("http://localhost.evil.example/x", undefined), DEFAULT_WEB_ORIGIN);
  assert.equal(printOrigin("http://127.0.0.1.nip.io/x", ""), DEFAULT_WEB_ORIGIN);
  assert.equal(printOrigin("not a url", undefined), DEFAULT_WEB_ORIGIN);
});

test("a configured origin must be http(s)", () => {
  assert.equal(printOrigin("http://evil.example/", "file:///etc/passwd"), DEFAULT_WEB_ORIGIN);
  assert.equal(printOrigin("http://evil.example/", "javascript:alert(1)"), DEFAULT_WEB_ORIGIN);
  assert.equal(printOrigin("http://evil.example/", "not a url"), DEFAULT_WEB_ORIGIN);
  assert.equal(printOrigin("file:///localhost/x", undefined), DEFAULT_WEB_ORIGIN);
});

test("the print URL is a fixed path plus the validated selection only", () => {
  const sel = parseSelection({ tickers: "nvda,BAD!!,aapl", title: "Q3\u0000 review", for: "x&y=z" });
  const url = printUrl("http://localhost:3000", sel);
  assert.equal(url, "http://localhost:3000/briefing/print?tickers=NVDA%2CAAPL&title=Q3+review&for=x%26y%3Dz");
  const parsed = new URL(url);
  assert.equal(parsed.pathname, "/briefing/print");
  assert.deepEqual([...parsed.searchParams.keys()], ["tickers", "title", "for"]);
});

test("file names list validated tickers, at most six, then -etc", () => {
  assert.equal(briefingFilename(["NVDA"]), "riskdiff-briefing-NVDA.pdf");
  assert.equal(briefingFilename(["NVDA", "AAPL", "BRK.B"]), "riskdiff-briefing-NVDA-AAPL-BRK.B.pdf");
  assert.equal(briefingFilename(["A", "B", "C", "D", "E", "F"]), "riskdiff-briefing-A-B-C-D-E-F.pdf");
  assert.equal(briefingFilename(["A", "B", "C", "D", "E", "F", "G"]), "riskdiff-briefing-A-B-C-D-E-F-etc.pdf");
  assert.equal(briefingFilename([]), "riskdiff-briefing.pdf");
  assert.equal(briefingFilename(['x"; evil', "nvda", "AMD"]), "riskdiff-briefing-AMD.pdf");
});

test("the footer template carries the disclaimer and page numbers", () => {
  assert.match(FOOTER_TEMPLATE, /not changes in actual risk\. Not investment advice\./);
  assert.match(FOOTER_TEMPLATE, /class='pageNumber'/);
  assert.match(FOOTER_TEMPLATE, /class='totalPages'/);
  assert.match(FOOTER_TEMPLATE, /font-size:9pt/);
  assert.match(FOOTER_TEMPLATE, /#3e4a5f/);
});
