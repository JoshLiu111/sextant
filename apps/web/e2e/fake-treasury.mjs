// A stand-in for home.treasury.gov's Daily Treasury Par Yield Curve CSV, for e2e
// tests only. Playwright starts it and points the compute service at it with
// TREASURY_BASE_URL, so the real Treasury adapter runs end to end without the
// network. It serves the recorded CSVs the compute tests use
// (apps/compute/tests/fixtures/treasury/<year>.csv), with the same routing rules
// as RecordedTreasury in apps/compute/tests/treasury_fixtures.py: a year without
// a recording answers 200 with an empty body, like Treasury for a future year.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.TREASURY_PORT || 9501);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/treasury/", import.meta.url));
const CSV_PATH = /^\/resource-center\/data-chart-center\/interest-rates\/daily-treasury-rates\.csv\/(\d{4})\/all$/;

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ status: "ok" }));
  }
  const match = CSV_PATH.exec(url.pathname);
  const params = url.searchParams;
  if (!match || params.get("type") !== "daily_treasury_yield_curve" || params.get("_format") !== "csv") {
    res.writeHead(404, { "content-type": "text/plain" });
    return res.end("Not found");
  }
  let body = "";
  try {
    body = await readFile(`${FIXTURES}${match[1]}.csv`, "utf8");
  } catch {
    // No recording for this year: Treasury answers an empty body.
  }
  res.writeHead(200, { "content-type": "text/csv; charset=UTF-8" });
  res.end(body);
}).listen(PORT, "127.0.0.1");
