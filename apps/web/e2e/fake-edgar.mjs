// A stand-in for SEC EDGAR, for e2e tests only. Playwright starts it (see
// playwright.config.ts) and points the compute service at it with
// EDGAR_BASE_URL, so the Company Health Check runs end to end on the recorded
// fixtures in apps/compute/tests/fixtures/edgar and never calls sec.gov.
//
// Serves the EDGAR paths the adapter uses (404 if not recorded):
//   GET /files/company_tickers.json
//   GET /api/xbrl/companyfacts/CIK##########.json
//   GET /api/xbrl/frames/<taxonomy>/<Tag>/<unit>/<period>.json   (screener)
//   GET /submissions/CIK##########.json                           (a company's filings)
//   GET /cgi-bin/browse-edgar?action=getcurrent&type=<form>       (latest filings feed)
// GET /health answers 200 so Playwright knows it is up.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.EDGAR_PORT || 9500);
const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "../../compute/tests/fixtures/edgar");

async function serveFile(res, name, contentType = "application/json") {
  try {
    const body = await readFile(join(FIXTURES, name));
    res.writeHead(200, { "content-type": contentType });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("Not found");
  }
}

createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  if (path === "/health") {
    res.writeHead(200, { "content-type": "text/plain" });
    return res.end("ok");
  }
  if (!req.headers["user-agent"]) {
    // Like the real EDGAR: an undeclared client is refused.
    res.writeHead(403, { "content-type": "text/plain" });
    return res.end("Forbidden");
  }
  if (path === "/files/company_tickers.json") return serveFile(res, "company_tickers.json");
  const match = /^\/api\/xbrl\/companyfacts\/(CIK\d{10}\.json)$/.exec(path);
  if (match) return serveFile(res, match[1]);
  const frame = /^\/api\/xbrl\/(frames\/[\w-]+\/\w+\/[\w-]+\/CY\d{4}(?:Q\dI?)?\.json)$/.exec(path);
  if (frame) return serveFile(res, frame[1]);
  const submissions = /^\/(submissions\/CIK\d{10}\.json)$/.exec(path);
  if (submissions) return serveFile(res, submissions[1]);
  if (path === "/cgi-bin/browse-edgar" && url.searchParams.get("action") === "getcurrent") {
    const form = url.searchParams.get("type") || "all";
    if (/^[\w -]+$/.test(form)) {
      return serveFile(res, `getcurrent/${form}.atom`, "application/atom+xml; charset=ISO-8859-1");
    }
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("Not found");
}).listen(PORT, "127.0.0.1", () => {
  console.log(`fake EDGAR on http://127.0.0.1:${PORT}`);
});
