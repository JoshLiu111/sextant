// A stand-in for the FRED API (api.stlouisfed.org/fred), for e2e tests only.
// Playwright starts it and points the compute service at it with
// FRED_API_BASE_URL, so the real FRED adapter runs end to end without the
// network or a real key. It serves the recorded responses the compute tests
// use (apps/compute/tests/fixtures/fred), with the same routing rules as
// RecordedFred in apps/compute/tests/fred_fixtures.py.

import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.FRED_PORT || 9500);
const FIXTURES = fileURLToPath(new URL("../../compute/tests/fixtures/fred/", import.meta.url));
const FOLDERS = { "/fred/series": "series", "/fred/series/observations": "observations" };

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/health") return send(res, 200, { status: "ok" });
  if (!url.searchParams.get("api_key")) {
    return send(res, 400, { error_code: 400, error_message: "Bad Request.  Variable api_key is not set." });
  }
  if (url.searchParams.get("file_type") !== "json") {
    return send(res, 400, { error_code: 400, error_message: "Bad Request.  Expected file_type=json." });
  }
  const folder = FOLDERS[url.pathname];
  const id = (url.searchParams.get("series_id") || "").replace(/[^A-Za-z0-9]/g, "");
  try {
    if (!folder || !id) throw new Error("unknown");
    send(res, 200, JSON.parse(await readFile(`${FIXTURES}${folder}/${id}.json`, "utf8")));
  } catch {
    send(res, 400, { error_code: 400, error_message: "Bad Request.  The series does not exist." });
  }
}).listen(PORT, "127.0.0.1");
