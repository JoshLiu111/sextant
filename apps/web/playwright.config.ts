import { defineConfig, devices } from "@playwright/test";

// Starts both halves: the FastAPI compute service and the Next.js frontend.
// Ports are overridable so several checkouts can run e2e side by side:
//   WEB_PORT=3100 COMPUTE_PORT=8100 npm run test:e2e
// Set PW_REUSE_SERVERS=1 to reuse dev servers you already started yourself.
const WEB_PORT = Number(process.env.WEB_PORT || 3000);
const COMPUTE_PORT = Number(process.env.COMPUTE_PORT || 8000);
const isCI = !!process.env.CI;
const reuse = !isCI && process.env.PW_REUSE_SERVERS === "1";
const computeUrl = `http://127.0.0.1:${COMPUTE_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: isCI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run uvicorn main:app --host 127.0.0.1 --port ${COMPUTE_PORT}`,
      cwd: "../compute",
      url: `${computeUrl}/api/compute/health`,
      reuseExistingServer: reuse,
    },
    {
      // Production build in CI; dev server locally for speed.
      command: isCI
        ? `npm run build && npm run start -- -H 127.0.0.1 -p ${WEB_PORT}`
        : `npm run dev -- -H 127.0.0.1 -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: reuse,
      timeout: 180_000,
      env: { COMPUTE_URL: computeUrl },
    },
  ],
});
