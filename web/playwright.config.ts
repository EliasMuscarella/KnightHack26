import { defineConfig } from "@playwright/test";

/**
 * Smoke test against the PRODUCTION build (not the dev server):
 *   API:  RISKDIFF_ALLOW_FIXTURE= uv run uvicorn api.main:app --port 8000
 *   Web:  npm run build && PORT=3000 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm start
 *   Test: npm run test:e2e        (BASE_URL / RISKDIFF_API_URL override the defaults)
 * The browser is the Chromium that ships with this environment (PLAYWRIGHT_CHROMIUM_PATH), so no
 * download happens at install time.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:3000",
    viewport: { width: 1440, height: 900 },
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH ?? "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    },
  },
});
