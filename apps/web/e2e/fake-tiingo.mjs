// A stand-in for the Tiingo API (api.tiingo.com), for e2e tests only.
// Playwright starts it and points the compute service at it with
// TIINGO_BASE_URL.
//
// GET /api/test answers the way real Tiingo does (checked 2026-11-22): always
// HTTP 200, with a message saying whether the token worked. Tokens starting
// with "good" are valid. A token starting with "outage" makes it answer 503, to
// stand in for Tiingo being down. Anything else is rejected.
//
// GET /tiingo/daily/<ticker>/prices serves the recorded responses the compute
// tests use (apps/compute/tests/fixtures/tiingo/daily: aapl, msft, spy; 30
// trading days from 2024-01-02), filtered by startDate/endDate, with the same
// rules as FakeTiingo in apps/compute/tests/tiingo_fixtures.py: 403 "Invalid
// token." for a token that isn't "good…", 404 for any other ticker.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.TIINGO_PORT || 9600);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/tiingo/daily/", import.meta.url));
const KNOWN = new Set(["aapl", "msft", "spy"]);

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

async function prices(res, url, token, ticker) {
  if (!token.startsWith("good")) return send(res, 403, { detail: "Invalid token." });
  if (!KNOWN.has(ticker)) return send(res, 404, { detail: `Error: Ticker '${ticker}' not found` });
  const start = url.searchParams.get("startDate") || "0000";
  const end = url.searchParams.get("endDate") || "9999";
  const rows = JSON.parse(await readFile(`${FIXTURES}${ticker}.json`, "utf8"));
  send(res, 200, rows.filter((r) => start <= r.date.slice(0, 10) && r.date.slice(0, 10) <= end));
}

createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") return send(res, 200, { status: "ok" });
  const auth = req.headers.authorization || "";
  const token = auth.replace(/^Token /, "");
  if (token.startsWith("outage")) return send(res, 503, { detail: "Service Unavailable" });
  const daily = /^\/tiingo\/daily\/([^/]+)\/prices$/.exec(url.pathname);
  if (daily) return void prices(res, url, token, decodeURIComponent(daily[1]));
  if (url.pathname !== "/api/test") return send(res, 404, { detail: "Not found." });
  if (!auth) return send(res, 200, { message: "'AUTHORIZATION header' was not set" });
  if (token.startsWith("good")) return send(res, 200, { message: "You successfully sent a request" });
  send(res, 200, { message: "Auth Token was not correct" });
}).listen(PORT, "127.0.0.1");
