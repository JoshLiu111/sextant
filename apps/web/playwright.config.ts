import { defineConfig, devices } from "@playwright/test";

// Starts both halves: the FastAPI compute service and the Next.js frontend.
// Ports are overridable so several checkouts can run e2e side by side:
//   WEB_PORT=3100 COMPUTE_PORT=8100 npm run test:e2e
// Set PW_REUSE_SERVERS=1 to reuse dev servers you already started yourself.
//
// Accounts: sign-in goes to a fake OIDC provider (e2e/fake-oidc.mjs) on
// OIDC_PORT (default COMPUTE_PORT + 1). FRED requests go to a fake FRED API
// (e2e/fake-fred.mjs) on FRED_PORT (default COMPUTE_PORT + 2), Treasury yield curve
// requests to a fake (e2e/fake-treasury.mjs) on TREASURY_PORT (default COMPUTE_PORT + 4),
// Tiingo key checks to a fake (e2e/fake-tiingo.mjs) on TIINGO_PORT (default COMPUTE_PORT + 6),
// World Bank requests to e2e/fake-world-bank.mjs on WORLD_BANK_PORT (default COMPUTE_PORT + 7)
// and ECB requests to e2e/fake-ecb.mjs on ECB_PORT (default COMPUTE_PORT + 8).
// The compute service uses
// E2E_DATABASE_URL if set (CI: the postgres service container); otherwise it
// starts a throwaway local Postgres (needs initdb/pg_ctl, e.g. Homebrew).
//
// SEC EDGAR: compute talks to e2e/fake-edgar.mjs on EDGAR_PORT (default
// COMPUTE_PORT + 3), which serves the recorded fixtures; sec.gov is never hit.
const WEB_PORT = Number(process.env.WEB_PORT || 3000);
const COMPUTE_PORT = Number(process.env.COMPUTE_PORT || 8000);
const OIDC_PORT = Number(process.env.OIDC_PORT || COMPUTE_PORT + 1);
const FRED_PORT = Number(process.env.FRED_PORT || COMPUTE_PORT + 2);
const EDGAR_PORT = Number(process.env.EDGAR_PORT || COMPUTE_PORT + 3);
// SEC EDGAR: compute fetches from a fake (e2e/fake-edgar.mjs) serving recorded fixtures.
const edgar = {
  EDGAR_BASE_URL: `http://127.0.0.1:${EDGAR_PORT}`,
  SEC_USER_AGENT: "Sextant e2e admin@example.com",
  // The screener's default year follows the calendar; pin it to the recorded frames.
  SCREENER_DEFAULT_YEAR: "2025",
};
const TREASURY_PORT = Number(process.env.TREASURY_PORT || COMPUTE_PORT + 4);
// Tiingo: users' key checks go to a fake (e2e/fake-tiingo.mjs). PROVIDER_KEY_SECRET
// encrypts saved keys; test-only value.
const TIINGO_PORT = Number(process.env.TIINGO_PORT || COMPUTE_PORT + 6);
const tiingo = {
  TIINGO_BASE_URL: `http://127.0.0.1:${TIINGO_PORT}`,
  PROVIDER_KEY_SECRET: "e2e-provider-key-secret-not-for-production-0123456789",
  // The screener's 52-week price window ends today; pin it to the recorded prices.
  SCREENER_PRICES_AS_OF: "2026-11-20",
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
// FRED: compute fetches from a fake (e2e/fake-fred.mjs) serving recorded responses.
const fred = {
  FRED_API_KEY: "e2efakefredkeynotreal0000000000",
  FRED_API_BASE_URL: `http://127.0.0.1:${FRED_PORT}/fred`,
  // The fake has no rate limit, so skip the 2 requests/second throttle real FRED needs.
  FRED_MIN_INTERVAL_SECONDS: "0",
};
// Treasury: compute fetches the yield curve CSVs from a fake (e2e/fake-treasury.mjs).
const treasury = { TREASURY_BASE_URL: `http://127.0.0.1:${TREASURY_PORT}` };
// World Bank and ECB: compute fetches from fakes serving the recorded responses.
const WORLD_BANK_PORT = Number(process.env.WORLD_BANK_PORT || COMPUTE_PORT + 7);
const ECB_PORT = Number(process.env.ECB_PORT || COMPUTE_PORT + 8);
const worldBankAndEcb = {
  WORLD_BANK_BASE_URL: `http://127.0.0.1:${WORLD_BANK_PORT}`,
  ECB_BASE_URL: `http://127.0.0.1:${ECB_PORT}`,
};
// AI Explain: compute talks to a fake Claude Messages API (e2e/fake-anthropic.mjs)
// on ANTHROPIC_PORT (default COMPUTE_PORT + 5). The key is a dummy; the quota is small
// so the over-quota path is quick to reach.
const ANTHROPIC_PORT = Number(process.env.ANTHROPIC_PORT || COMPUTE_PORT + 5);
const ai = {
  ANTHROPIC_API_KEY: "e2e-fake-anthropic-key-not-real",
  ANTHROPIC_BASE_URL: `http://127.0.0.1:${ANTHROPIC_PORT}`,
  AI_DAILY_QUOTA: "3",
  // The only account allowed into the operator view (/operator).
  OPERATOR_EMAILS: "operator@example.test",
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
      command: "node e2e/fake-world-bank.mjs",
      url: `${worldBankAndEcb.WORLD_BANK_BASE_URL}/health`,
      reuseExistingServer: reuse,
      env: { WORLD_BANK_PORT: String(WORLD_BANK_PORT) },
    },
    {
      command: "node e2e/fake-ecb.mjs",
      url: `${worldBankAndEcb.ECB_BASE_URL}/health`,
      reuseExistingServer: reuse,
      env: { ECB_PORT: String(ECB_PORT) },
    },
    {
      command: "node e2e/fake-anthropic.mjs",
      url: `${ai.ANTHROPIC_BASE_URL}/health`,
      reuseExistingServer: reuse,
      env: { ANTHROPIC_PORT: String(ANTHROPIC_PORT) },
    },
    {
      command: "node e2e/fake-tiingo.mjs",
      url: `${tiingo.TIINGO_BASE_URL}/health`,
      reuseExistingServer: reuse,
      env: { TIINGO_PORT: String(TIINGO_PORT) },
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
        ...fred,
        ...treasury,
        ...worldBankAndEcb,
        ...ai,
        ...tiingo,
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
