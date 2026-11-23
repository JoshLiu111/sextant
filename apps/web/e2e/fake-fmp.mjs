// A stand-in for the FMP "stable" API (financialmodelingprep.com), for e2e tests
// only. Playwright starts it and points the compute service at it with
// FMP_BASE_URL.
//
// The key comes in the `apikey` header. Keys starting with "good" are valid; a
// key starting with "outage" makes it answer 503, to stand in for FMP being
// down. Anything else answers 401 with FMP's real "Invalid API KEY" body
// (probed 2026-11-22).
//
// GET /stable/quote: the key check. GET /stable/historical-price-eod/full and
// /stable/dividends serve the recorded responses the compute tests use
// (apps/compute/tests/fixtures/fmp: aapl, msft, spy; 30 trading days from
// 2024-01-02, newest first), with the same rules as FakeFmp in
// apps/compute/tests/fmp_fixtures.py: an unknown symbol answers 402 with the
// same plain-text body as a symbol outside the plan (real FMP free plan,
// checked 2026-11-23).

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.FMP_PORT || 9510);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/fmp/", import.meta.url));
const KNOWN = new Set(["aapl", "msft", "spy"]);
const INVALID_KEY = {
  "Error Message":
    "Invalid API KEY. Feel free to create a Free API Key or visit https://site.financialmodelingprep.com/faqs?search=why-is-my-api-key-invalid for more information.",
};

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const PREMIUM =
  "Premium Query Parameter: 'Special Endpoint : This value set for 'symbol' is not available under your current subscription please visit our subscription page to upgrade your plan at https://financialmodelingprep.com/developer/docs/pricing'";

async function rows(dataset, symbol) {
  return JSON.parse(await readFile(`${FIXTURES}${dataset}/${symbol}.json`, "utf8"));
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") return send(res, 200, { status: "ok" });
  const key = req.headers.apikey || "";
  if (key.startsWith("outage")) return send(res, 503, { "Error Message": "Service Unavailable" });
  if (!key.startsWith("good")) return send(res, 401, INVALID_KEY);
  const symbol = (url.searchParams.get("symbol") || "").toLowerCase();
  if (url.pathname === "/stable/quote") return send(res, 200, symbol ? [{ symbol: symbol.toUpperCase(), price: 130 }] : []);
  const prices = url.pathname === "/stable/historical-price-eod/full" || url.pathname === "/stable/dividends";
  if (prices && !KNOWN.has(symbol)) {
    res.writeHead(402, { "content-type": "text/plain" });
    return res.end(PREMIUM);
  }
  if (url.pathname === "/stable/historical-price-eod/full") {
    const from = url.searchParams.get("from") || "0000";
    const to = url.searchParams.get("to") || "9999";
    return send(res, 200, (await rows("historical-price-eod", symbol)).filter((r) => from <= r.date && r.date <= to));
  }
  if (url.pathname === "/stable/dividends") return send(res, 200, await rows("dividends", symbol));
  send(res, 404, { "Error Message": "Not found." });
}).listen(PORT, "127.0.0.1");
