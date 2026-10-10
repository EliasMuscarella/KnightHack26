/**
 * Smoke test: every page renders with zero console errors, zero uncaught exceptions and no Next.js
 * error overlay. Pages: home, every company in /companies, the top three change pages of each,
 * Trends and methodology. Trends must not say "not connected" while the store reports `ok`.
 *
 * Nothing here is company-specific: the company list and the change ids come from the API.
 */
import { expect, test, type Page } from "@playwright/test";

const API = (process.env.RISKDIFF_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const TOP_CHANGES = 3;

interface Capture {
  consoleErrors: string[];
  pageErrors: string[];
}

function capture(page: Page): Capture {
  const c: Capture = { consoleErrors: [], pageErrors: [] };
  page.on("console", (msg) => {
    if (msg.type() === "error") c.consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => c.pageErrors.push(String(err)));
  return c;
}

async function visit(page: Page, path: string, c: Capture) {
  const res = await page.goto(path, { waitUntil: "networkidle" });
  expect(res?.ok(), `${path} responded ${res?.status()}`).toBeTruthy();
  // Next.js error overlay / app error boundary
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  await expect(page.getByText("Application error", { exact: false })).toHaveCount(0);
  expect(c.pageErrors, `uncaught exceptions on ${path}`).toEqual([]);
  expect(c.consoleErrors, `console errors on ${path}`).toEqual([]);
}

async function apiJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

test("home, methodology and trends render without errors", async ({ page }) => {
  const c = capture(page);
  await visit(page, "/", c);
  await visit(page, "/methodology", c);
  await visit(page, "/trends", c);
  const health = await apiJson<{ remote: string }>("/store/health");
  if (health.remote === "ok") {
    await expect(page.getByText("not connected", { exact: false })).toHaveCount(0);
  }
  // The Trends page either shows content or an explicit, non-error empty state; never a blank page.
  await expect(page.locator("main")).not.toBeEmpty();
});

test("every company page and its top change pages render without errors", async ({ page }) => {
  test.setTimeout(10 * 60_000);
  const { companies } = await apiJson<{ companies: { ticker: string }[] }>("/companies");
  expect(companies.length, "the API lists no companies").toBeGreaterThan(0);
  for (const { ticker } of companies) {
    const c = capture(page);
    await visit(page, `/c/${encodeURIComponent(ticker)}`, c);
    const comparison = await apiJson<{ changes: { id: string }[] }>(`/comparison/${encodeURIComponent(ticker)}`);
    for (const change of comparison.changes.slice(0, TOP_CHANGES)) {
      await visit(page, `/c/${encodeURIComponent(ticker)}/${encodeURIComponent(change.id)}`, c);
    }
  }
});

test("the Trends company set matches /companies", async ({ page }) => {
  const c = capture(page);
  const { companies } = await apiJson<{ companies: { ticker: string }[] }>("/companies");
  const trends = await apiJson<{ companies: { ticker: string }[] }>("/trends");
  expect(new Set(trends.companies.map((x) => x.ticker))).toEqual(new Set(companies.map((x) => x.ticker)));
  await visit(page, "/trends", c);
});
