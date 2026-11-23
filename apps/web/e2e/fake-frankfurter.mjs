// A stand-in for api.frankfurter.dev (v2 rates), for e2e tests only. Playwright
// starts it and points the compute service at it with FRANKFURTER_BASE_URL, so
// the real Frankfurter adapter runs end to end without the network. It serves
// the recorded responses the compute tests use
// (apps/compute/tests/fixtures/frankfurter/<BASE>-<QUOTE>-<YEAR>.json), with the
// same routing rules as RecordedFrankfurter in
// apps/compute/tests/frankfurter_fixtures.py: a currency outside SUPPORTED
// answers the recorded 422, and a year without a recording answers 200 [].

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.FRANKFURTER_PORT || 9509);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/frankfurter/", import.meta.url));
const SUPPORTED = new Set(["EUR", "USD", "GBP", "JPY", "CHF", "CAD"]);

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") return json(res, 200, { status: "ok" });
  if (url.pathname !== "/v2/rates") return json(res, 404, { status: 404, message: "not found" });
  const params = url.searchParams;
  const base = (params.get("base") || "").toUpperCase();
  const quote = (params.get("quotes") || "").toUpperCase();
  for (const code of [base, quote]) {
    if (!SUPPORTED.has(code)) {
      const body = await readFile(`${FIXTURES}invalid-XYZ.json`, "utf8");
      return json(res, 422, body.replace("XYZ", code));
    }
  }
  const year = (params.get("from") || "").slice(0, 4);
  let body = "[]";
  try {
    body = await readFile(`${FIXTURES}${base}-${quote}-${year}.json`, "utf8");
  } catch {
    // No recording for this year: Frankfurter answers an empty list.
  }
  json(res, 200, body);
}).listen(PORT, "127.0.0.1");
