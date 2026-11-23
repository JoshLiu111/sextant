import { defineConfig, devices } from "@playwright/test";

// Starts both halves: the FastAPI compute service and the Next.js frontend.
// Ports are overridable so several checkouts can run e2e side by side:
//   WEB_PORT=3100 COMPUTE_PORT=8100 npm run test:e2e
// Set PW_REUSE_SERVERS=1 to reuse dev servers you already started yourself.
//
// Accounts: sign-in goes to a fake OIDC provider (e2e/fake-oidc.mjs) on
// OIDC_PORT (default COMPUTE_PORT + 1). FRED requests go to a fake FRED API
// (e2e/fake-fred.mjs) on FRED_PORT (default COMPUTE_PORT + 2), Treasury yield curve
// requests to a fake (e2e/fake-treasury.mjs) on TREASURY_PORT (default COMPUTE_PORT + 3).
// The compute service uses
// E2E_DATABASE_URL if set (CI: the postgres service container); otherwise it
// starts a throwaway local Postgres (needs initdb/pg_ctl, e.g. Homebrew).
const WEB_PORT = Number(process.env.WEB_PORT || 3000);
const COMPUTE_PORT = Number(process.env.COMPUTE_PORT || 8000);
const OIDC_PORT = Number(process.env.OIDC_PORT || COMPUTE_PORT + 1);
const FRED_PORT = Number(process.env.FRED_PORT || COMPUTE_PORT + 2);
const TREASURY_PORT = Number(process.env.TREASURY_PORT || COMPUTE_PORT + 3);
const isCI = !!process.env.CI;
const reuse = !isCI && process.env.PW_REUSE_SERVERS === "1";
const computeUrl = `http://127.0.0.1:${COMPUTE_PORT}`;

// Test-only values; real ones live in env vars on Vercel, never in the repo.
const auth = {
  SESSION_SECRET: "e2e-session-secret-not-for-production-0123456789",
  GOOGLE_CLIENT_ID: "e2e-client-id",
  GOOGLE_CLIENT_SECRET: "e2e-client-secret",
  OIDC_ISSUER: `http://127.0.0.1:${OIDC_PORT}`,
};
// FRED: compute fetches from a fake (e2e/fake-fred.mjs) serving recorded responses.
const fred = {
  FRED_API_KEY: "e2efakefredkeynotreal0000000000",
  FRED_API_BASE_URL: `http://127.0.0.1:${FRED_PORT}/fred`,
};
// Treasury: compute fetches the yield curve CSVs from a fake (e2e/fake-treasury.mjs).
const treasury = { TREASURY_BASE_URL: `http://127.0.0.1:${TREASURY_PORT}` };
const uvicorn = `uv run uvicorn main:app --host 127.0.0.1 --port ${COMPUTE_PORT}`;
const e2eDatabaseUrl = process.env.E2E_DATABASE_URL;

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
      command: "node e2e/fake-oidc.mjs",
      url: `${auth.OIDC_ISSUER}/.well-known/openid-configuration`,
      reuseExistingServer: reuse,
      env: { OIDC_PORT: String(OIDC_PORT), ...auth },
    },
    {
      command: "node e2e/fake-fred.mjs",
      url: `http://127.0.0.1:${FRED_PORT}/health`,
      reuseExistingServer: reuse,
      env: { FRED_PORT: String(FRED_PORT) },
    },
    {
      command: "node e2e/fake-treasury.mjs",
      url: `${treasury.TREASURY_BASE_URL}/health`,
      reuseExistingServer: reuse,
      env: { TREASURY_PORT: String(TREASURY_PORT) },
    },
    {
      command: e2eDatabaseUrl
        ? uvicorn
        : `uv run python scripts/ephemeral_postgres.py -- ${uvicorn}`,
      cwd: "../compute",
      url: `${computeUrl}/api/compute/health`,
      reuseExistingServer: reuse,
      // SIGTERM lets the ephemeral Postgres wrapper clean up its cluster.
      gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
      env: {
        SESSION_SECRET: auth.SESSION_SECRET,
        ...fred,
        ...treasury,
        ...(e2eDatabaseUrl ? { DATABASE_URL: e2eDatabaseUrl } : {}),
      },
    },
    {
      // Production build in CI; dev server locally for speed.
      command: isCI
        ? `npm run build && npm run start -- -H 127.0.0.1 -p ${WEB_PORT}`
        : `npm run dev -- -H 127.0.0.1 -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: reuse,
      timeout: 180_000,
      env: { COMPUTE_URL: computeUrl, ...auth },
    },
  ],
});
