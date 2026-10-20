import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config (PLAN.md §12, R36). Two app instances, both LLM_MOCK=true with a
 * throwaway DB:
 *
 * - BASE_URL: the instance every mutating test uses. Tests assert relative changes
 *   or set up their own state, so they pass in any order.
 * - FRESH_BASE_URL: an instance nothing ever writes to, so the fresh-start scenario
 *   ($10k cash, default watchlist) holds no matter what ran before it.
 *
 * test/docker-compose.test.yml sets both. Outside Docker they default to
 * http://localhost:8000; then fresh-start only passes against a just-started app.
 */
export const BASE_URL = process.env.BASE_URL ?? "http://localhost:8000";
export const FRESH_BASE_URL = process.env.FRESH_BASE_URL ?? BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  // Mutating tests share one portfolio; parallel trades would break each other's
  // cash deltas. One worker keeps them isolated without ordering them.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
