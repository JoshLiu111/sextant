import { defineConfig, devices } from "@playwright/test";

// Starts both halves: the FastAPI compute service and the Next.js frontend.
// Ports are overridable so several checkouts can run e2e side by side:
//   WEB_PORT=3100 COMPUTE_PORT=8100 npm run test:e2e
// Set PW_REUSE_SERVERS=1 to reuse dev servers you already started yourself.
//
// Accounts: sign-in goes to a fake OIDC provider (e2e/fake-oidc.mjs) on
// OIDC_PORT (default COMPUTE_PORT + 1). The compute service uses
// E2E_DATABASE_URL if set (CI: the postgres service container); otherwise it
// starts a throwaway local Postgres (needs initdb/pg_ctl, e.g. Homebrew).
//
// SEC EDGAR: compute talks to e2e/fake-edgar.mjs on EDGAR_PORT (default
// COMPUTE_PORT + 2), which serves the recorded fixtures; sec.gov is never hit.
const WEB_PORT = Number(process.env.WEB_PORT || 3000);
const COMPUTE_PORT = Number(process.env.COMPUTE_PORT || 8000);
const OIDC_PORT = Number(process.env.OIDC_PORT || COMPUTE_PORT + 1);
// SEC EDGAR is replaced by e2e/fake-edgar.mjs serving recorded fixtures.
const EDGAR_PORT = Number(process.env.EDGAR_PORT || COMPUTE_PORT + 2);
const edgar = {
  EDGAR_BASE_URL: `http://127.0.0.1:${EDGAR_PORT}`,
  SEC_USER_AGENT: "Sextant e2e admin@example.com",
};
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
      command: "node e2e/fake-edgar.mjs",
      url: `${edgar.EDGAR_BASE_URL}/health`,
      reuseExistingServer: reuse,
      env: { EDGAR_PORT: String(EDGAR_PORT) },
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
        ...edgar,
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
