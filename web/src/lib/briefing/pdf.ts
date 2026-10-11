/**
 * Server-only: renders the bare print route (`/briefing/print`) to a PDF with a local Chromium
 * driven by playwright-core. Used by `app/api/briefing.pdf/route.ts` (and, for the file name, by
 * the preview page). Playwright loads lazily on the first render.
 *
 * Safety rules:
 * - The URL Chromium opens is built only from validated values: a fixed origin (the request's own
 *   origin when it is localhost, else RISKDIFF_WEB_ORIGIN, else http://localhost:3000), a fixed
 *   path and `selectionQuery(...)` of a parsed selection. Raw query input never reaches it.
 * - One render at a time (a module-level queue), 45 s per render, 60 s maximum wait in the queue.
 * - Errors become a status code and a short message; no stack traces leave this module.
 */
import type { Browser } from "playwright-core";

import { TICKER_PATTERN } from "@/lib/ticker";

import { selectionQuery, type BriefingSelection } from "./selection";

export const DEFAULT_WEB_ORIGIN = "http://localhost:3000";
export const RENDER_TIMEOUT_MS = 45_000;
export const QUEUE_WAIT_MS = 60_000;
const GOTO_TIMEOUT_MS = 40_000;
/** Close an idle browser after this long so Chrome does not linger between demos. */
const BROWSER_IDLE_MS = 5 * 60_000;
const MAX_FILENAME_TICKERS = 6;

export const PDF_UNAVAILABLE = "PDF rendering is unavailable on this machine";
export const PDF_EMPTY = "None of these companies are in the library";
export const PDF_BUSY = "Another briefing is being rendered. Try again in a minute.";
export const PDF_FAILED = "The briefing could not be rendered as a PDF";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"]);

/**
 * Origin Chromium loads the print route from. The request's own origin only when it is
 * localhost / 127.0.0.1 (http or https); otherwise a configured http(s) origin; otherwise the
 * default dev origin. A Host header can therefore never point the renderer elsewhere.
 */
export function printOrigin(requestUrl: string, envOrigin: string | undefined | null): string {
  try {
    const u = new URL(requestUrl);
    if ((u.protocol === "http:" || u.protocol === "https:") && LOCAL_HOSTS.has(u.hostname)) return u.origin;
  } catch {
    // fall through
  }
  if (envOrigin) {
    try {
      const e = new URL(envOrigin.trim());
      if (e.protocol === "http:" || e.protocol === "https:") return e.origin;
    } catch {
      // fall through
    }
  }
  return DEFAULT_WEB_ORIGIN;
}

/** `${origin}/briefing/print?tickers=…`, from validated values only. */
export function printUrl(origin: string, sel: Pick<BriefingSelection, "tickers" | "title" | "preparedFor">): string {
  return `${origin}/briefing/print?${selectionQuery(sel)}`;
}

/** "riskdiff-briefing-NVDA-AAPL.pdf"; at most six tickers, then "-etc". Invalid tickers are skipped. */
export function briefingFilename(tickers: readonly string[]): string {
  const valid = tickers.filter((t) => TICKER_PATTERN.test(t));
  if (valid.length === 0) return "riskdiff-briefing.pdf";
  const shown = valid.slice(0, MAX_FILENAME_TICKERS).join("-");
  return `riskdiff-briefing-${shown}${valid.length > MAX_FILENAME_TICKERS ? "-etc" : ""}.pdf`;
}

/** Chromium's footer template: a fixed string (no input), 9pt, interface font, page x / y. */
export const FOOTER_TEMPLATE =
  '<div style="box-sizing:border-box;width:100%;padding:0 14mm;display:flex;justify-content:space-between;align-items:baseline;gap:8mm;' +
  "font-family:'Public Sans',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;font-size:9pt;line-height:1.3;color:#3e4a5f;\">" +
  "<span>RiskDiff measures changes in disclosed risk language, not changes in actual risk. Not investment advice.</span>" +
  "<span style=\"white-space:nowrap\"><span class='pageNumber'></span> / <span class='totalPages'></span></span>" +
  "</div>";

export type RenderResult = { ok: true; pdf: Buffer; ms: number } | { ok: false; status: 404 | 500 | 503; error: string };

class RenderError extends Error {
  readonly status: 404 | 500 | 503;
  readonly publicMessage: string;
  constructor(status: 404 | 500 | 503, publicMessage: string, detail: string) {
    super(detail);
    this.status = status;
    this.publicMessage = publicMessage;
  }
}

// ---------------------------------------------------------------------------------------
// Browser and queue state lives on globalThis so dev hot reloads reuse it (no orphaned Chrome).
// ---------------------------------------------------------------------------------------

interface PdfState {
  browser: Promise<Browser> | null;
  tail: Promise<void>;
  idleTimer: ReturnType<typeof setTimeout> | null;
}

const g = globalThis as typeof globalThis & { __riskdiffBriefingPdf?: PdfState };
const state: PdfState = (g.__riskdiffBriefingPdf ??= { browser: null, tail: Promise.resolve(), idleTimer: null });

async function launchBrowser(): Promise<Browser> {
  // Loaded on first use, so importing the pure helpers above never loads Playwright.
  let chromium: typeof import("playwright-core").chromium;
  try {
    ({ chromium } = await import("playwright-core"));
  } catch {
    throw new RenderError(503, PDF_UNAVAILABLE, "playwright-core could not be loaded");
  }
  // The installed Google Chrome first (nothing to download), then a Playwright-managed Chromium.
  try {
    return await chromium.launch({ channel: "chrome", headless: true });
  } catch {
    // try the next option
  }
  try {
    return await chromium.launch({ headless: true });
  } catch {
    throw new RenderError(503, PDF_UNAVAILABLE, "no Chrome or Playwright Chromium could be launched");
  }
}

async function getBrowser(): Promise<Browser> {
  if (state.browser) {
    const existing = await state.browser.catch(() => null);
    if (existing?.isConnected()) return existing;
    state.browser = null;
  }
  const pending = launchBrowser();
  state.browser = pending;
  try {
    const browser = await pending;
    browser.on("disconnected", () => {
      if (state.browser === pending) state.browser = null;
    });
    return browser;
  } catch (e) {
    if (state.browser === pending) state.browser = null;
    throw e;
  }
}

async function closeBrowser(): Promise<void> {
  const pending = state.browser;
  state.browser = null;
  if (!pending) return;
  try {
    await (await pending).close();
  } catch {
    // already gone
  }
}

function scheduleIdleClose() {
  if (state.idleTimer) clearTimeout(state.idleTimer);
  state.idleTimer = setTimeout(() => {
    state.idleTimer = null;
    void closeBrowser();
  }, BROWSER_IDLE_MS);
  state.idleTimer.unref?.();
}

function delay(ms: number): Promise<"timeout"> {
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve("timeout"), ms);
    t.unref?.();
  });
}

/**
 * Run `fn` when every earlier render has finished. Waits at most `waitMs` for the slot; a render
 * that times out still releases it. Order is first come, first served.
 */
async function inRenderSlot<T>(fn: () => Promise<T>, waitMs: number): Promise<T> {
  const previous = state.tail;
  let release!: () => void;
  const mine = new Promise<void>((resolve) => (release = resolve));
  state.tail = previous.then(() => mine);
  const waited = await Promise.race([previous.then(() => "ready" as const), delay(waitMs)]);
  if (waited === "timeout") {
    release();
    throw new RenderError(503, PDF_BUSY, "render queue busy");
  }
  if (state.idleTimer) {
    clearTimeout(state.idleTimer);
    state.idleTimer = null;
  }
  try {
    return await fn();
  } finally {
    scheduleIdleClose();
    release();
  }
}

async function renderOnce(url: string): Promise<Buffer> {
  const browser = await getBrowser();
  const context = await browser.newContext({ colorScheme: "light", viewport: { width: 1280, height: 1024 } });
  let timedOut = false;
  // Closing the context aborts whatever page call is pending, so the render cannot outlive its budget.
  const timer = setTimeout(() => {
    timedOut = true;
    void context.close().catch(() => undefined);
  }, RENDER_TIMEOUT_MS);
  try {
    // The stored theme choice wins over the OS preference in layout.tsx's theme script (THEME_KEY in ThemeToggle.tsx).
    await context.addInitScript(() => {
      try {
        window.localStorage.setItem("riskdiff-theme", "light");
      } catch {
        // storage blocked: colorScheme "light" still selects the light theme
      }
    });
    const page = await context.newPage();
    const response = await page.goto(url, { waitUntil: "networkidle", timeout: GOTO_TIMEOUT_MS });
    if (response && response.status() >= 500) throw new Error(`print route answered ${response.status()}`);
    await page.waitForSelector('[data-briefing-ready="1"]', { state: "attached", timeout: 15_000 });
    await page.evaluate(async () => {
      await document.fonts.ready;
    });
    if (await page.$('[data-briefing-empty="1"]')) throw new RenderError(404, PDF_EMPTY, "no companies in the library");
    return await page.pdf({
      format: "Letter",
      printBackground: true,
      preferCSSPageSize: false,
      displayHeaderFooter: true,
      margin: { top: "16mm", bottom: "18mm", left: "14mm", right: "14mm" },
      headerTemplate: "<span></span>",
      footerTemplate: FOOTER_TEMPLATE,
      tagged: true,
    });
  } catch (e) {
    if (e instanceof RenderError) throw e;
    if (timedOut) throw new RenderError(503, PDF_FAILED, `render exceeded ${RENDER_TIMEOUT_MS} ms`);
    throw e;
  } finally {
    clearTimeout(timer);
    await context.close().catch(() => undefined);
  }
}

function oneLine(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  return msg.split("\n")[0].slice(0, 200);
}

/** Render the print route at `url` (built by `printUrl`) to a Letter PDF. Never throws. */
export async function renderBriefingPdf(url: string): Promise<RenderResult> {
  const started = Date.now();
  try {
    const pdf = await inRenderSlot(() => renderOnce(url), QUEUE_WAIT_MS);
    return { ok: true, pdf, ms: Date.now() - started };
  } catch (e) {
    if (e instanceof RenderError) {
      if (e.status !== 404) console.error(`[briefing.pdf] ${e.status}: ${oneLine(e)}`);
      return { ok: false, status: e.status, error: e.publicMessage };
    }
    // Unknown failure: drop the browser so the next request starts clean.
    console.error(`[briefing.pdf] 500: ${oneLine(e)}`);
    await closeBrowser();
    return { ok: false, status: 500, error: PDF_FAILED };
  }
}
